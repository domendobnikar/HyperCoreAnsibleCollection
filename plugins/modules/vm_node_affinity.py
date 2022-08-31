#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2022, XLAB Steampunk <steampunk@xlab.si>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
module: vm_node_affinity

author:
  - Polona Mihalič (@PolonaM)
short_description: Update virtual machine's node affinity
description:
  - Module updates selected virtual machine's node affinity.
version_added: 0.0.1
extends_documentation_fragment:
  - scale_computing.hypercore.cluster_instance
seealso: []
options:
  vm_name:
    description:
      - Virtual machine name
      - Used to identify selected virtual machine by name
    type: str
    required: True
  strict_affinity:
    description:
      - Enable or disable strict enforcement of affinity strategy. The VirDomain will only run on preferred or backup node.
      - If strict_affinity is set to true and nodes are not provided, the preferred_node's uuid will be set to node_uuid provided in VM.
        If node_uuid is not set, strict_affinity will be set to False.
    type: bool
    required: True
  preferred_node:
    description:
      - Preferred node to run the VirDomain
      - Can be set by node_uuid, backplane_ip, lan_ip or peer_id
      - One of the options should be enough. In case that all are set, logical AND operation will be used.
        Task will return FAIL in case, that node can not be uniquely identified.
    type: dict
    suboptions:
      node_uuid:
        description: Unique identifier of preferred node
        type: str
      backplane_ip:
        description: Backplane IP of the preferred node
        type: str
      lan_ip:
        description: Lan IP of the preferred node
        type: str
      peer_id:
        description: Peer ID of the preffered node
        type: int
  backup_node:
    description:
      - Backup node in the event that preferred_node is unavailable
      - Can be set by node_uuid, backplane_ip, lan_ip or peer_id
      - One of the options should be enough. In case that all are set, logical AND operation will be used.
        Task will return FAIL in case, that node can not be uniquely identified.
    type: dict
    suboptions:
      node_uuid:
        description: Unique identifier of backup node
        type: str
      backplane_ip:
        description: Backplane IP of the backup node
        type: str
      lan_ip:
        description: Lan IP of the backup node
        type: str
      peer_id:
        description: Peer ID of the backup node
        type: int
"""

EXAMPLES = r"""
- name: Set VM node affinity by node uuid
  scale_computing.hypercore.vm_node_affinity:
    vm_name: demo-vm
    strict_affinity: true
    preferred_node:
      node_uuid: "412a3e85-8c21-4138-a36e-789eae3548a3"
    backup_node:
      node_uuid: "3dd52913-4e60-46fa-8ac6-07ba0b2155d2"

- name: Set VM node affinity by backplane IP, lan IP, or peer ID
  scale_computing.hypercore.vm_node_affinity:
    vm_name: demo-vm
    strict_affinity: true
    preferred_node:
      backplane_ip: "10.0.0.1"
      lan_ip: "10.0.0.1"
      peer_id: 1
    backup_node:
      backplane_ip: "10.0.0.2"
      lan_ip: "10.0.0.2"
      peer_id: 2
"""

RETURN = r"""
msg:
  description:
    - Info about node affinity update status.
  returned: always
  type: str
  sample:
    msg: "Node affinity successfully updated."
"""

from ansible.module_utils.basic import AnsibleModule

from ..module_utils import arguments, errors
from ..module_utils.client import Client
from ..module_utils.rest_client import RestClient
from ..module_utils.vm import VM
from ..module_utils.node import Node
from ..module_utils.utils import get_query


def get_node_uuid(module, node, rest_client):
    node_uuid = ""  # if node is not provided
    if module.params[node] is not None:  # if node is provided
        query = get_query(
            module.params[node],
            "node_uuid",  # uuid is checked if it really exists
            "backplane_ip",
            "lan_ip",
            "peer_id",
            ansible_hypercore_map=dict(
                node_uuid="uuid",
                backplane_ip="backplaneIP",
                lan_ip="lanIP",
                peer_id="peerID",
            ),
        )
        node = Node.get_node(query, rest_client, must_exist=True)
        node_uuid = node.node_uuid
    return node_uuid


def run(module, rest_client):
    vm_before = VM.get_by_name(
        module.params, rest_client, must_exist=True
    )  # get vm from vm_name
    strict_affinity = module.params["strict_affinity"]
    preferred_node_uuid = get_node_uuid(module, "preferred_node", rest_client)
    backup_node_uuid = get_node_uuid(module, "backup_node", rest_client)

    if (
        vm_before.node_affinity["strict_affinity"] != strict_affinity
        or vm_before.node_affinity["preferred_node"]["node_uuid"] != preferred_node_uuid
        or vm_before.node_affinity["backup_node"]["node_uuid"] != backup_node_uuid
    ):
        msg = "Node affinity successfully updated."

        if (
            module.params["strict_affinity"] is True
            and preferred_node_uuid == ""
            and backup_node_uuid == ""
        ):
            preferred_node_uuid = vm_before.node_uuid
            msg = "No nodes provided, VM's preferredNodeUUID set to it's nodeUUID."

            if vm_before.node_uuid == "":
                strict_affinity = False
                msg = "No nodes provided and VM's nodeUUID not set, strict affinity set to false"

        payload = {
            "affinityStrategy": {
                "strictAffinity": strict_affinity,
                "preferredNodeUUID": preferred_node_uuid,
                "backupNodeUUID": backup_node_uuid,
            }
        }
        endpoint = "{0}/{1}".format("/rest/v1/VirDomain", vm_before.uuid)
        rest_client.update_record(endpoint, payload, module.check_mode)
        vm_after = VM.get_by_name(module.params, rest_client, must_exist=True)
        if module.check_mode:
            vm_after.node_affinity = dict(
                strict_affinity=strict_affinity,
                preferred_node=Node.get_node(
                    {"uuid": preferred_node_uuid}, rest_client
                ).to_ansible()
                if preferred_node_uuid != ""
                else None,
                backup_node=Node.get_node(
                    {"uuid": backup_node_uuid}, rest_client
                ).to_ansible()
                if backup_node_uuid != ""
                else None,
            )

        return (
            True,
            msg,
            dict(before=vm_before.node_affinity, after=vm_after.node_affinity),
        )

    else:
        msg = "Node affinity already set to desired values."
        return (
            False,
            msg,
            dict(before=vm_before.node_affinity, after=vm_before.node_affinity),
        )


def main():
    module = AnsibleModule(
        supports_check_mode=True,
        argument_spec=dict(
            arguments.get_spec("cluster_instance"),
            vm_name=dict(
                type="str",
                required=True,
            ),
            strict_affinity=dict(
                type="bool",
                required=True,
            ),
            preferred_node=dict(
                type="dict",
                options=dict(
                    node_uuid=dict(type="str"),
                    backplane_ip=dict(type="str"),
                    lan_ip=dict(type="str"),
                    # option types need to be provided so that in case of "peer_id: "{{ nodes.records[0].peer_id }}"" peer_id is int and not str
                    peer_id=dict(type="int"),
                ),
            ),
            backup_node=dict(
                type="dict",
                options=dict(
                    node_uuid=dict(type="str"),
                    backplane_ip=dict(type="str"),
                    lan_ip=dict(type="str"),
                    peer_id=dict(type="int"),
                ),
            ),
        ),
    )

    try:
        client = Client(
            host=module.params["cluster_instance"]["host"],
            username=module.params["cluster_instance"]["username"],
            password=module.params["cluster_instance"]["password"],
        )
        rest_client = RestClient(client)
        changed, msg, diff = run(module, rest_client)
        module.exit_json(changed=changed, msg=msg, diff=diff)
    except errors.ScaleComputingError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()
