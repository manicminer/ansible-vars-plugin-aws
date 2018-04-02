# Ansible AWS Vars Plugin

This is a drop-in plugin for Ansible 2.5+ which provides the following:

* Searches one or more AWS accounts for VPC, subnet, security group and ELB target group details,
* Matches tags of all these resources with configured set of tag names, then
* Builds a hierarchical dictionary of resources mapped by tag values,
* All the above information is made available to all hosts managed by Ansible by means of native host variables
* Bonus feature: brings native support for multiple AWS accounts with automatic account switching once per playbook based on extra vars passed at runtime.

Read below for more detailed explanations.


# How To Use

This module is shipped with a skeleton structure with the intention that you can test it right out of this repository. An example AWS config file is given with `aws.ini` and wrapper scripts `ansible.sh`/`playbook.sh` to set some useful environment variables for you.

However, it's more likely that you already have an Ansible project, in which case all you need to do it copy the `vars_plugins/` directory into your project root (relative to your playbooks). The plugin should be automatically detected by Ansible.

If you have a different vars_plugin directory configured in `ansible.cfg`, just drop `aws.py` and `aws.yml` it into that directory instead.

You'll want to change the settings in `vars_plugin/aws.yml` to match your environment. These settings are:

`regions:`  
This is a list of regions where the plugin will look for resources

`use_cache: [yes|no]`  
Whether or not to cache resource details after retrieving them. Recommended.

`cache_max_age: 600`  
How long to cache resource details before retrieving them again from AWS. Defaults to 600 seconds (10 mins).

`cache_env_vars:`  
A list of environment variables to inspect and save the values of when caching resource details. Should the values of any of these environment variables change, the cache will be invalidated.

`aws_profiles:`  
Can be either a list of profile names, or a dictionary having profile names as keys, and each value being a dictionary of extra variables to inspect when selecting a default account for the current playbook (see below). When a list, no matching is performed and no credentials are set.

`vpc_tags:`  
A list of tag keys to match when building a dictionary of VPC IDs. When specified, the global host variable `vpc_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictionary is set.

`subnet_tags:`  
A list of tag keys to match when building a dictionary of subnet IDs. When specified, the global host variable `subnet_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictionary is set.

`security_group_tags:`  
A list of tag keys to match when building a dictionary of security group IDs. When specified, the global host variable `security_group_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictionary is set.

`elb_target_group_tags:`  
A list of tag keys to match when building a dictionary of ELB target groups IDs. When specified, the global host variable `elb_target_group_arns` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictionary is set.


# Global Variables

The following host variables are set by this plugin for every host Ansible attempts to manage, essentially these are global variables usable anywhere within your playbooks or roles.

- `aws_account_ids` - a dictionary of AWS account IDs with profile name as keys and account ID as values.
- `aws_profile` - the currently selected AWS profile when matched by extra vars
- `elb_target_groups` - a dictionary of ELB target groups with resource ID as keys and dictionary of useful information as values
- `elb_target_group_arns` - a complex nested dictionary of ELB target group ARNs denominated by matched tag values
- `security_groups` - a dictionary of security groups with resource ID as keys and dictionary of useful information as values
- `security_group_ids` - a complex nested dictionary of security group IDs denominated by matched tag values
- `subnets` - a dictionary of subnets with resource ID as keys and dictionary of useful information as values
- `subnet_ids` - a complex nested dictionary of subnet IDs denominated by matched tag values
- `vpcs` - a dictionary of VPCs with resource ID as keys and dictionary of useful information as values
- `vpc_ids` - a complex nested dictionary of VPC IDs denominated by matched tag values


# AWS Resources

In the configuration file for this plugin, you can specify a list of tag keys for each type of supported resource. When the plugin runs (right before playbook execution) it fetches resource descriptions from AWS and organizes them into hierarchical dictionaries based on the values of the configured tag keys.

For example, given this configuration:

```yaml
subnet_tags:
  - project
  - env
  - tier
```

and having subnets in your AWS account(s) like:

Subnet ID       | Tag: project | Tag: env | Tag: tier
--------------- | ------------ | -------- | ---------
subnet-aabbcc12 | apollo       | prod     | app
subnet-aabbcc13 | apollo       | prod     | app
subnet-aabbcc14 | apollo       | prod     | data
subnet-aabbcc15 | apollo       | prod     | data
subnet-aabbcc16 | apollo       | prod     | lb
subnet-aabbcc17 | apollo       | prod     | lb
subnet-aabbcc18 | apollo       | staging  | app
subnet-aabbcc19 | apollo       | staging  | app
subnet-aabbcc20 | apollo       | staging  | data
subnet-aabbcc21 | apollo       | staging  | data
subnet-aabbcc22 | apollo       | staging  | lb
subnet-aabbcc23 | apollo       | staging  | lb
subnet-aabbcc24 | manhattan    | prod     | app
subnet-aabbcc25 | manhattan    | prod     | app
subnet-aabbcc26 | manhattan    | prod     | data
subnet-aabbcc27 | manhattan    | prod     | data
subnet-aabbcc28 | manhattan    | prod     | lb
subnet-aabbcc29 | manhattan    | prod     | lb
subnet-aabbcc30 | manhattan    | staging  | app
subnet-aabbcc31 | manhattan    | staging  | app
subnet-aabbcc32 | manhattan    | staging  | data
subnet-aabbcc33 | manhattan    | staging  | data
subnet-aabbcc34 | manhattan    | staging  | lb
subnet-aabbcc35 | manhattan    | staging  | lb

You'll end up with a global dictionary like:

```yaml
subnet_ids:
  us-east-1:
    apollo:
      prod:
        app:
          - subnet-aabbcc12
          - subnet-aabbcc13
        data:
          - subnet-aabbcc14
          - subnet-aabbcc15
        lb:
          - subnet-aabbcc16
          - subnet-aabbcc17
      staging
        app:
          - subnet-aabbcc18
          - subnet-aabbcc19
        data:
          - subnet-aabbcc20
          - subnet-aabbcc21
        lb:
          - subnet-aabbcc22
          - subnet-aabbcc23
    manhattan:
      prod:
        app:
          - subnet-aabbcc24
          - subnet-aabbcc25
        data:
          - subnet-aabbcc26
          - subnet-aabbcc27
        lb:
          - subnet-aabbcc28
          - subnet-aabbcc29
      staging
        app:
          - subnet-aabbcc30
          - subnet-aabbcc31
        data:
          - subnet-aabbcc32
          - subnet-aabbcc33
        lb:
          - subnet-aabbcc34
          - subnet-aabbcc35
```

Which you can reference like this:

```yaml
- hosts: localhost
  connection: local
  tasks:
    - ec2:
        instance_type: t2.micro
        vpc_subnet_id: "{{ subnet_ids['us-east-1']['manhattan']['staging']['app'] | random }}"
        state: present
```

The same pattern is implemented for VPCs, subnets, security groups and ELB target groups, alowing you to specify and target resources in your playbooks without hard coding resource IDs, without using `*_facts` modules everywhere, and without needing to know the exact names of every resource. It's important to note that these resources can reside in any number of AWS accounts, as long as they can be reached by your Ansible control host.


# Multi Account Support

The multi account support provided by this plugin comes in two flavors.

1. With multiple accounts configured as AWS profiles on your Ansible control host, the plugin will traverse all accounts to retrieve resource information.
2. Additionally, with rules configured in the configuration file, it will inspect any extra vars you specify when running your playbook and *automatically select* one of the profiles to use for your playbook execution. This is accomplished by requesting temporary credentials from STS and exporting them within Ansible as a set of `AWS_*` environment variables. These exported env vars are consumed by Boto2 and Boto3-based modules alike.

Note that resources are still retrieved from all accounts, even when auto-selection is configured.

For example, given this configuration:

```yaml
aws_profiles:
  staging:
    env:
      - development
      - staging
  production:
    env: production
```

And the following playbook invocation:

```
$ ansible-playbook do-a-thing.yml -e env=staging
```

The plugin would select the `staging` profile, obtain temporary credentials using that profile, then export those credentials to be automatically used by any AWS modules/tasks in your playbook.

Any number of extra vars can be specified for each profile, and all must match for a profile to be selected. For example, you might have something like this, where each project resides in its own AWS account, and development happens in a default account (possibly the developers' own accounts):

```yaml
aws_profiles:
  default:
    env: development
  apollo-staging:
    env: staging
    project: apollo
  apollo-production:
    env: production
    project: apollo
  manhattan-staging:
    env: staging
    project: manhattan
  manhattan-production:
    env: production
    project: manhattan
  ops:
    env: ops
```

The primary limitation of this approach is that the AWS account is selected once, prior to playbook execution. However, it's possible to trivially use a different account for a given task by requesting credentials with the `sts_assume_role` module and specifying them explicitly for a task, which overrides the environment variables set by this plugin.

# Putting It All Together

By passing the `env`, `project` and `service` extra vars to `ansible-playbook`, you can invoke the multi-account support to auto-select the correct AWS account to use, and use those same extra vars to pick the right resources. In the example below, the instance will be launched in the desired account, with the appropriate security group and subnet for the service type.

```
$ ansible-playbook launch.yml -e env=staging -e project=manhattan -e service=app
```
```yaml
- hosts: localhost
  connection: local

  vars:
    region: us-east-1

  tasks:

    - name: Launch instance
      ec2:
        region: "{{ region }}"
        instance_tags:
          env: "{{ env }}"
          project: "{{ project }}"
          service: "{{ service }}"
        instance_type: t2.micro
        group_id: "{{ security_group_ids[region][project][env][service] }}"
        vpc_subnet_id: "{{ subnet_ids[region][project][env][service] | random }}"
        wait: yes
      register: result_ec2

    - name: Register in inventory
      add_host:
        name: "{{ item.private_ip }}"
        groups: launch
        ec2_id: "{{ item.id }}"
      when: item.state == 'running'
      with_flattened:
        - "{{ result_ec2.results | map(attribute='instances') | list }}"

    - name: Wait for SSH
      wait_for:
        host: "{{ item }}"
        port: 22
        timeout: 420
        state: started
      with_items: "{{ groups.launch }}"


- hosts: launch
  roles:
    - role: common
```

# Also Note

## Regions

For maximum control, this plugin requires that regions be explicitly configured. The configuration setting `regions` is a list. All regions configured will be searched for resources, and the resulting dictionaries are nested by region.

## Resource Caching

Just like Ansible's EC2 inventory script, this plugin caches all the resource information it finds, in order to speed up subsequent playbook executions. The cache can be disabled by setting `use_cache: no` in the configuration file, and the cache timeout (which defaults to 10 minutes) can be specified [in seconds] with the `cache_max_age` setting.

It's possible that factors outside of Ansible could invalidate cached information, so it's also possible to configure one or more environment variables, the values of which will be saved and if they change between playbook runs, the cache will be automatically invalidated.

