#!/bin/bash

DIR="$(cd `dirname $0` && pwd)"

ANSIBLE_VERSION="$(ansible --version | head -1 | awk '{print $2}')"
[[ "${ANSIBLE_VERSION:0:3}" != "2.5" ]] && echo -e "Supported Ansible version: 2.5\nYou are using version: ${ANSIBLE_VERSION:0:3}\n\nPlease install the supported version" >&2 && exit 1

[[ -z "${ANSIBLE_CONFIG}" ]] && export ANSIBLE_CONFIG="${DIR}/ansible.cfg"
[[ -z "${ANSIBLE_INVENTORY}" ]] && export ANSIBLE_INVENTORY="${DIR}/inventory"
[[ -z "${EC2_INI_PATH}" ]] && export EC2_INI_PATH="${DIR}/inventory/ec2.ini"
[[ -z "${ANSIBLE_ROLES_PATH}" ]] && export ANSIBLE_ROLES_PATH="${DIR}/roles"
[[ -z "${ANSIBLE_VARS_PLUGINS}" ]] && export ANSIBLE_VARS_PLUGINS="${DIR}/vars_plugins"
[[ -z "${AWS_CONFIG_FILE}" ]] && export AWS_CONFIG_FILE="$(readlink -f "${DIR}/aws.ini")"

echo Running from directory: ${DIR}
echo AWS configuration: ${AWS_CONFIG_FILE}
echo Using inventory from: ${ANSIBLE_INVENTORY}
echo EC2 inventory config: ${EC2_INI_PATH}
echo

time ansible-playbook -vv "$@"
exit $?

# vim: set ts=2 sts=2 sw=2 et:
