from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    vars: aws
    version_added: "2.5"
    short_description: Retrieves VPC, subnet, security group and load balancer information from AWS
    description:
        - Connects to AWS for each of the configured accounts and regions
        - Discovers VPC, subnet, security group and ELB target group IDs
        - Makes these IDs available as global variables for all hosts
        - Caches the above data locally for the configured period (default: 5 mins)
        - Optionally matches extra vars with configured rules to identify which account should be used for the current playbook, then establishes a temporary session and exports credentials as environment variables for consumption by AWS modules
    notes:
        - Requires boto3
        - Configuration should be placed in aws.yml in the same directory as this file
'''

try:
    import boto3
    import botocore.exceptions
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

import argparse
import json, os, re, time, yaml
from ansible.errors import AnsibleParserError
from ansible.plugins.vars import BaseVarsPlugin

DIR = os.path.dirname(os.path.realpath(__file__))

def parse_cli_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--extra-vars', action='append')
    parser.add_argument('--flush-cache', action='store_true', default=False)
    opts, unknown = parser.parse_known_args()
    args = dict()
    if opts.extra_vars:
        args['extra_vars'] = dict(e.split('=') for e in opts.extra_vars if '=' in e)
    if opts.flush_cache:
        args['flush_cache'] = True
    return args


def load_config():
    ''' Test for configuration file and return configuration dictionary '''

    with open(os.path.join(DIR, 'aws.yml'), 'r') as stream:
        try:
            config = yaml.safe_load(stream)
            return config
        except yaml.YAMLError as e:
            raise AnsibleParserError('Failed to read aws.yml: {0}'.format(e))


def append_leaf(d, l, v):
    i = l.pop(0)
    if len(l):
        if i not in d:
            d[i] = dict()
        d[i] = append_leaf(d[i], l, v)
    else:
        if i not in d:
            d[i] = []
        d[i].append(v)
    return d


class VarsModule(BaseVarsPlugin):

    CACHE_MAX_AGE = 600

    def __init__(self, *args):
        ''' Load configuration and determine cache path '''

        super(VarsModule, self).__init__(*args)

        self.config = load_config()
        cli_args = parse_cli_args()
        self.extra_vars = cli_args.get('extra_vars', dict())
        self.flush_cache = cli_args.get('flush_cache', False)

        self.cache_path = os.path.expanduser('~/.ansible/tmp/aws-vars.cache')
        self.env_cache_path = os.path.expanduser('~/.ansible/tmp/aws-vars.env')
        self.use_cache = self.config.get('use_cache', True) in [True, 'yes', 'y', 'true']
        self.cache_env_vars = self.config.get('cache_env_vars', [])
        self._connect_profiles()
        self._export_credentials()


    def _connect_profiles(self):
        for profile in self._profiles():
            self._init_session(profile)


    def _export_credentials(self):
        self.aws_profile = None
        profiles = self.config.get('aws_profiles', ['default'])

        if isinstance(profiles, dict):
            profiles_list = profiles.keys()
        else:
            profiles_list = profiles

        credentials = {profile: self._credentials(profile) for profile in profiles_list}

        profile_override = os.environ.get('ANSIBLE_AWS_PROFILE')
        default_profile = None
        if profile_override:
            if profile_override in profiles:
                default_profile = profile_override
        elif isinstance(profiles, dict) and self.extra_vars:
            for profile, rules in profiles.iteritems():
                if isinstance(rules, dict):
                    rule_matches = {var: False for var in rules.keys()}
                    for var, vals in rules.iteritems():
                        if isinstance(vals, basestring):
                            vals = [vals]
                        if var in self.extra_vars and self.extra_vars[var] in vals:
                            rule_matches[var] = True
                    if all(m == True for m in rule_matches.values()):
                        default_profile = profile
                        break

        if default_profile:
            self.aws_profile = default_profile
            os.environ['AWS_ACCESS_KEY_ID'] = credentials[default_profile].access_key
            os.environ['AWS_SECRET_ACCESS_KEY'] = credentials[default_profile].secret_key
            os.environ['AWS_SECURITY_TOKEN'] = credentials[default_profile].token
            os.environ['AWS_SESSION_TOKEN'] = credentials[default_profile].token

        cleaner = re.compile('[^a-zA-Z0-9_]')
        for profile, creds in credentials.iteritems():
            profile_clean = cleaner.sub('_', profile).upper()
            os.environ['{}_AWS_ACCESS_KEY_ID'.format(profile_clean)] = creds.access_key
            os.environ['{}_AWS_SECRET_ACCESS_KEY'.format(profile_clean)] = creds.secret_key
            os.environ['{}_AWS_SECURITY_TOKEN'.format(profile_clean)] = creds.token
            os.environ['{}_AWS_SESSION_TOKEN'.format(profile_clean)] = creds.token


    def _init_session(self, profile):
        if not hasattr(self, 'sessions'):
            self.sessions = dict()
        try:
            self.sessions[profile] = boto3.Session(profile_name=profile)
        except botocore.exceptions.ProfileNotFound as e:
            if profile == 'default':
                self.sessions[profile] = boto3.Session()
            else:
                raise


    def _session(self, profile):
        return self.sessions[profile]


    def _credentials(self, profile):
        return self.sessions[profile].get_credentials().get_frozen_credentials()


    def _profiles(self):
        profiles = self.config.get('aws_profiles', ['default'])
        if isinstance(profiles, dict):
            return profiles.keys()
        else:
            return [p for p in profiles]


    def _get_account_ids(self):
        ''' Retrieve AWS account ID '''
        self.account_ids = {p: self.sessions[p].client('sts').get_caller_identity()['Account'] for p in self._profiles()}


    def _get_vpc_ids(self):
        ''' Retrieve all VPC details from AWS API '''

        self.vpcs = dict()
        self.vpc_ids = dict()
        tag_list = self.config.get('vpc_tags', [])
        for region in self.config.get('regions'):
            for profile in self._profiles():
                client = self._session(profile).client('ec2', region_name=region)
                vpcs_result = client.describe_vpcs()
                if vpcs_result and 'Vpcs' in vpcs_result and len(vpcs_result['Vpcs']):
                    for vpc in vpcs_result['Vpcs']:
                        self.vpcs[vpc['VpcId']] = dict(
                            cidr_block=vpc['CidrBlock'],
                            is_default=vpc['IsDefault'],
                            instance_tenancy=vpc['InstanceTenancy'],
                            profile=profile,
                            region=region,
                            state=vpc['State'],
                        )
                        if 'Tags' in vpc:
                            tags = dict((t['Key'], t['Value']) for t in vpc['Tags'])
                            self.vpcs[vpc['VpcId']]['tags'] = tags
                            if tag_list:
                                ind = [tags[t] for t in tag_list if t in tags]
                                if len(ind) == len(tag_list):
                                    self.vpc_ids = append_leaf(self.vpc_ids, [region] + ind, vpc['VpcId'])


    def _get_subnets(self):
        ''' Retrieve all subnet details from AWS API '''

        self.subnets = dict()
        self.subnet_ids = dict()
        tag_list = self.config.get('subnet_tags', [])
        for region in self.config.get('regions', []):
            for profile in self._profiles():
                client = self._session(profile).client('ec2', region_name=region)
                subnets_result = client.describe_subnets()
                if subnets_result and 'Subnets' in subnets_result and len(subnets_result['Subnets']):
                    for subnet in subnets_result['Subnets']:
                        self.subnets[subnet['SubnetId']] = dict(
                            cidr=subnet['CidrBlock'],
                            zone=subnet['AvailabilityZone'],
                            profile=profile,
                            region=region,
                            vpc_id=subnet['VpcId'],
                        )
                        if 'Tags' in subnet:
                            tags = dict((t['Key'], t['Value']) for t in subnet['Tags'])
                            self.subnets[subnet['SubnetId']]['tags'] = tags
                            if tag_list:
                                ind = [tags[t] for t in tag_list if t in tags]
                                if len(ind) == len(tag_list):
                                    self.subnet_ids = append_leaf(self.subnet_ids, [region] + ind, subnet['SubnetId'])


    def _get_security_groups(self):
        ''' Retrieve all security group details from AWS API '''
        self.security_groups = dict()
        self.security_group_ids = dict()
        tag_list = self.config.get('security_group_tags', [])
        for region in self.config.get('regions'):
            for profile in self._profiles():
                client = self._session(profile).client('ec2', region_name=region)
                groups_result = client.describe_security_groups()
                if groups_result and 'SecurityGroups' in groups_result and len(groups_result['SecurityGroups']):
                    for group in groups_result['SecurityGroups']:
                        self.security_groups[group['GroupId']] = dict(
                            name=group['GroupName'],
                            profile=profile,
                            region=region,
                        )
                        if 'VpcId' in group:
                            self.security_groups[group['GroupId']]['type'] = 'vpc'
                            self.security_groups[group['GroupId']]['vpc_id'] = group['VpcId']
                        else:
                            self.security_groups[group['GroupId']]['type'] = 'classic'
                        if 'Tags' in group:
                            tags = dict((t['Key'], t['Value']) for t in group['Tags'])
                            self.security_groups[group['GroupId']]['tags'] = tags
                            if tag_list:
                                ind = [tags[t] for t in tag_list if t in tags]
                                if len(ind) == len(tag_list):
                                    self.security_group_ids = append_leaf(self.security_group_ids, [region] + ind, group['GroupId'])


    def _get_elb_target_groups(self):
        ''' Retrieve all LB target group details from AWS API '''

        self.elb_target_groups = dict()
        self.elb_target_group_arns = dict()
        tag_list = self.config.get('elb_target_group_tags', [])
        for region in self.config.get('regions'):
            for profile in self._profiles():
                client = self._session(profile).client('elbv2', region_name=region)
                groups_result = client.describe_target_groups()
                if groups_result and 'TargetGroups' in groups_result and len(groups_result['TargetGroups']):
                    groups = dict()
                    for group in groups_result['TargetGroups']:
                        groups[group['TargetGroupArn']] = dict(
                            name=group['TargetGroupName'],
                            protocol=group['Protocol'],
                            port=group['Port'],
                            load_balancer_arns=group['LoadBalancerArns'],
                            profile=profile,
                            region=region,
                            target_type=group['TargetType'],
                            vpc_id=group['VpcId'],
                        )
                    self.elb_target_groups.update(groups)
                    tags_result = client.describe_tags(ResourceArns=groups.keys())
                    if tags_result and 'TagDescriptions' in tags_result and len(tags_result['TagDescriptions']):
                        for group in tags_result['TagDescriptions']:
                            if 'Tags' in group:
                                tags = dict((t['Key'], t['Value']) for t in group['Tags'])
                                self.elb_target_groups[group['ResourceArn']]['tags'] = tags
                                if tag_list:
                                    ind = [tags[t] for t in tag_list if t in tags]
                                    if len(ind) == len(tag_list):
                                        self.elb_target_group_arns = append_leaf(self.elb_target_group_arns, [region] + ind, group['ResourceArn'])


    def _get_vars_from_api(self):
        ''' Retrieve AWS resources from AWS API '''

        self._get_account_ids()
        self._get_vpc_ids()
        self._get_security_groups()
        self._get_subnets()
        self._get_elb_target_groups()

        return dict(
            aws_account_ids=self.account_ids,
            elb_target_groups=self.elb_target_groups,
            elb_target_group_arns=self.elb_target_group_arns,
            security_groups=self.security_groups,
            security_group_ids=self.security_group_ids,
            subnets=self.subnets,
            subnet_ids=self.subnet_ids,
            vpcs=self.vpcs,
            vpc_ids=self.vpc_ids,
        )


    def _get_vars_from_cache(self):
        ''' Load AWS resources from JSON cache file '''

        cache = open(self.cache_path, 'r')
        aws_vars = json.load(cache)
        return aws_vars


    def _check_env_var_cache(self):
        ''' Check the environment variable cache to see if any values have changed '''
        if not os.path.isfile(self.env_cache_path):
            return False

        env_cache = open(self.env_cache_path, 'r')
        env_data = json.load(env_cache)
        for v in self.cache_env_vars:
            if v not in env_data or env_data[v] != os.environ.get(v, ''):
                return False
        return True


    def _is_cache_valid(self):
        ''' Determines if the cache files have expired, or if it is still valid '''

        if self.use_cache and not self.flush_cache:
            if os.path.isfile(self.cache_path):
                mod_time = os.path.getmtime(self.cache_path)
                current_time = time.time()
                if (mod_time + self.config.get('cache_max_age', self.CACHE_MAX_AGE)) > current_time:
                    if self.cache_env_vars:
                        return self._check_env_var_cache()
                    else:
                        return True
        return False


    def _save_cache(self, data):
        ''' Write AWS vars in JSON format to cache file '''

        if self.use_cache:
            cache = open(self.cache_path, 'w')
            json_data = json.dumps(data)
            cache.write(json_data)
            cache.close()

            if self.cache_env_vars:
                env_cache = open(self.env_cache_path, 'w')
                env_data = {v: os.environ.get(v, '') for v in self.cache_env_vars}
                json_env_data = json.dumps(env_data)
                env_cache.write(json_env_data)
                env_cache.close()


    def get_vars(self, loader, path, entities, cache=True):
        if not HAS_BOTO3:
            raise AnsibleParserError('AWS vars plugin requires boto3')

        #raise AnsibleParserError(self.extra_vars)

        super(VarsModule, self).get_vars(loader, path, entities)

        if self._is_cache_valid():
            data = self._get_vars_from_cache()
        else:
            data = self._get_vars_from_api()
            self._save_cache(data)

        data['aws_profile'] = self.aws_profile
        return data


# vim: set ft=python ts=4 sts=4 sw=4 et:
