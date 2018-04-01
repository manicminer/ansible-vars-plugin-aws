# Ansible AWS Vars Plugin

This is a drop-in plugin for Ansible 2.5+ which provides the following:

* Searches one or more AWS accounts for VPC, subnet, security group and ELB target group details,
* Matches tags of all these resources with configured set of tag names, then
* Builds a hierarchical dictionary of resources mapped by tag values,
* All the above information is made available to all hosts managed by Ansible by means of native host variables
* Bonus feature: brings native support for multiple AWS accounts with automatic account switching once per playbook based on extra vars passed at runtime.

Read below for more detailed explanations.


# How To Use

THis module is shipped with a skeleton structure with the intention that you can test it right out of this repository. However, it's more likely that you already have an Ansible project, in which case all you need to do it copy the `vars_plugins/` directory into your project root (relative to your playbooks). The plugin should be automatically detected by Ansible.

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
A list of tag keys to match when building a dictionary of VPC IDs. When specified, the global host variable `vpc_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictonary is set.

`subnet_tags:`  
A list of tag keys to match when building a dictionary of subnet IDs. When specified, the global host variable `subnet_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictonary is set.

`security_group_tags:`  
A list of tag keys to match when building a dictionary of security group IDs. When specified, the global host variable `security_group_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictonary is set.

`elb_target_group_tags:`  
A list of tag keys to match when building a dictionary of ELB target groups IDs. When specified, the global host variable `elb_target_group_ids` contains a nested dictionary of resource IDs denominated by tag values. If not specified, no dictonary is set.


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
subnet-aabbcc18 | apollo       | stage    | app
subnet-aabbcc19 | apollo       | stage    | app
subnet-aabbcc20 | apollo       | stage    | data
subnet-aabbcc21 | apollo       | stage    | data
subnet-aabbcc22 | apollo       | stage    | lb
subnet-aabbcc23 | apollo       | stage    | lb
subnet-aabbcc24 | manhattan    | prod     | app
subnet-aabbcc25 | manhattan    | prod     | app
subnet-aabbcc26 | manhattan    | prod     | data
subnet-aabbcc27 | manhattan    | prod     | data
subnet-aabbcc28 | manhattan    | prod     | lb
subnet-aabbcc29 | manhattan    | prod     | lb
subnet-aabbcc30 | manhattan    | stage    | app
subnet-aabbcc31 | manhattan    | stage    | app
subnet-aabbcc32 | manhattan    | stage    | data
subnet-aabbcc33 | manhattan    | stage    | data
subnet-aabbcc34 | manhattan    | stage    | lb
subnet-aabbcc35 | manhattan    | stage    | lb

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
      stage:
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
      stage:
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

The same pattern is implemented for VPCs, subnets, security groups and ELB target groups, alowing you to specify and target resources in your playbooks without hard coding resource IDs, without using `*_facts` modules everywhere, and without needing to know the exact names of every resource. It's important to note that these resources can reside in any number of AWS accounts, as long as they can be reached by your Ansible control host.


# Multi Account Support

The multi account support provided by this plugin comes in two flavors.

1. With multiple accounts configured as AWS profiles on your Ansible control host, the plugin will traverse all accounts to retrieve resource information.
2. Additionally, with rules configured in the configuration file, it will inspect any extra vars you specify when running your playbook and *automatically select* one of the profiles to use for your playbook execution. This is accomplished by requesting temporary credentials from STS and exporting them within Ansible as a set of `AWS_*` environment variables. These exported env vars are consumed by Boto2 and Boto3-based modules alike.

The primary limitation of this approach is that the AWS account is selected once, prior to playbook execution. However, it's possible to trivially use a different account for a given task by requesting credentials with the `sts_assume_role` module and specifying them explicitly for a task, which overrides the environment variables set by this plugin.

# Regions

For maximum control, this plugin requires that regions be explicitly configured. The configuration setting `regions` is a list. All regions configured will be searched for resources, and the resulting dictionaries are nested by region.

# Resource Caching

Just like Ansible's EC2 inventory script, this plugin caches all the resource information it finds, in order to speed up subsequent playbook executions. The cache can be disabled by setting `use_cache: no` in the configuration file, and the cache timeout (which defaults to 10 minutes) can be specified [in seconds] with the `cache_max_age` setting.

It's possible that factors outside of Ansible could invalidate cached information, so it's also possible to configure one or more environment variables, the values of which will be saved and if they change between playbok runs, the cache will be automatically invalidated.

