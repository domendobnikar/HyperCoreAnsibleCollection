# -*- coding: utf-8 -*-
# Copyright: (c) 2023, XLAB Steampunk <steampunk@xlab.si>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
module: dns_config

author:
  - Ana Zobec (@anazobec)
short_description: Modify DNS configuration on HyperCore API
description:
  - Use this module to add to or delete from a DNS configuration on HyperCore API.
version_added: 1.2.0
extends_documentation_fragment:
  - scale_computing.hypercore.cluster_instance
seealso:
  - module: scale_computing.hypercore.dns_config_info
options:
  search_domains:
    type: list
    elements: str
    description:
      - List of DNS names to use as new DNS configuration or to add to DNS configuration.
      - If the configuration is added, then, if all of the provided DNS names already exist
        on HyperCore API, and DNS names on server are in correct order, there will be no changes made.
  dns_servers:
    type: list
    elements: str
    description:
      - List of DNS server IPs to use as new DNS configuration or to add to DNS configuration.
      - If the configuration is added, then, if all of the provided DNS names already exist
        on HyperCore API, and DNS server IPs on server are in correct order, there will be no changes made.
  state:
    type: str
    choices:
      - set
      - before
      - after
    required: True
    description:
      - With I(state=set), the DNS configuration entries are B(set to new) specified entries.
      - With I(state=before), the specified entries are B(prepended) to the existing DNS configuration.
      - With I(state=after), the specified entries are B(appended) to the existing DNS configuration.
notes:
 - C(check_mode) is not supported.
"""


EXAMPLES = r"""
- name: Add entry to existing DNS configuration
  scale_computing.hypercore.dns_config:
    search_domains:
      - example.domain1.com
      - example.domain2.com
    dns_servers:
      - 1.2.3.4
      - 5.6.7.8
    state: before  # or after

- name: Overwrite all the existing DNS configuration entries
  scale_computing.hypercore.dns_config:
    search_domains: []
    dns_servers: []
    state: set
"""

RETURN = r"""
results:
  description:
    - Output from modifying entries of the DNS configuration on HyperCore API.
  returned: success
  type: dict
  sample:
    uuid: "dnsconfig_guid"
    server_ips:
      - "1.1.1.1"
      - "1.0.0.1"
    search_domains: []
    latest_task_tag:
      completed: 1673966351
      created: 1673966345
      descriptionParameters: []
      formattedDescription: "DNSConfig Update"
      formattedMessage: ""
      messageParameters: []
      modified: 1673966351
      nodeUUIDs:
        - "32c5012d-7d7b-49b4-9201-70e02b0d8758"
      objectUUID: "dnsconfig_guid"
      progressPercent: 100
      sessionID: "b8c45c35-3349-49e0-9474-0edfa73a2162"
      state: "COMPLETE"
      taskTag: "396"
"""


from ansible.module_utils.basic import AnsibleModule

from ..module_utils.task_tag import TaskTag
from ..module_utils import arguments, errors
from ..module_utils.client import Client
from ..module_utils.rest_client import RestClient
from ..module_utils.dns_config import DNSConfig


def build_entry_list(
    api_entry_list: list,
    module_entry_list: list,
    state: str,
    module: AnsibleModule = None,  # use module param for debugging
) -> tuple[list, bool]:
    if module_entry_list is None:
        return api_entry_list, False

    if module_entry_list is not None:
        if state == "set":
            new_entry_list = module_entry_list
        elif state == "before":
            new_entry_list = module_entry_list + api_entry_list
        elif state == "after":
            new_entry_list = api_entry_list + module_entry_list

    new_entry_list = list(  # bring everything back to list
        # creates a dict from values in list: ensure there are no duplicates
        dict.fromkeys(
            # creates a list with removed empty values
            list(filter(None, new_entry_list))
        )
    )
    change_needed = new_entry_list != api_entry_list

    # this block is used for debugging
    if module:
        module.warn("new_entry_list: " + str(new_entry_list))
        module.warn("api_entry_list: " + str(api_entry_list))
        module.warn("change_needed: " + str(change_needed))

    return (
        new_entry_list,
        change_needed,
    )


def modify_dns_config(
    module: AnsibleModule, rest_client: RestClient
) -> tuple[bool, dict, dict]:
    # GET method to get the DNS Config by UUID
    dns_config = DNSConfig.get_by_uuid(module.params, rest_client)

    # If DNS config doesn't exist, raise an exception (error)
    if not dns_config:
        raise errors.ScaleComputingError("DNS Config: There is no DNS configuration.")

    # Otherwise, continue with modifying the configuration
    before = dns_config.to_ansible()
    old_state = DNSConfig.get_state(
        rest_client
    )  # get the state of DNS config before modification

    state = module.params["state"]  # state param value from module

    # Set action according to specified state param
    action = "create"
    if state != "set":
        action = "update"

    # Build entries for modifications
    new_dns_servers, dns_servers_change_needed = build_entry_list(
        before.get("server_ips"),
        module.params["dns_servers"],
        state,
    )
    new_search_domains, search_domains_change_needed = build_entry_list(
        before.get("search_domains"),
        module.params["search_domains"],
        state,
    )

    # Init return values and return if no changes were needed
    change, new_state, diff = (
        dns_servers_change_needed or search_domains_change_needed,
        old_state,
        dict(before=before, after=old_state),
    )
    if not change:
        return change, new_state, diff

    # Set the task tag
    # using builtin method getattr() to call either create_record or update_record method from rest_client
    # - pros: less if statements in code
    # update_record method uses method PATCH,
    # create_record method uses method POST.
    # [ NOTE: PUT method is not allowed on DNS Config ]
    task_tag = getattr(rest_client, "{0}_record".format(action))(
        endpoint="{0}/{1}".format("/rest/v1/DNSConfig", dns_config.uuid),
        payload=dict(searchDomains=new_search_domains, serverIPs=new_dns_servers),
        check_mode=module.check_mode,
    )

    TaskTag.wait_task(rest_client, task_tag)  # wait for the task to finish

    # Get the new state of DNS Config and return
    new_dns_config = DNSConfig.get_by_uuid(module.params, rest_client)
    after = new_dns_config.to_ansible()
    new_state, diff = DNSConfig.get_state(rest_client), dict(before=before, after=after)
    change = old_state != new_state

    return change, new_state, diff


def run(module: AnsibleModule, rest_client: RestClient) -> tuple[bool, dict, dict]:
    return modify_dns_config(module, rest_client)


def main() -> None:
    module = AnsibleModule(
        supports_check_mode=False,
        argument_spec=dict(
            arguments.get_spec("cluster_instance"),
            dns_servers=dict(
                type="list",
                elements="str",
                required=False,
            ),
            search_domains=dict(
                type="list",
                elements="str",
                required=False,
            ),
            state=dict(
                type="str",
                choices=["set", "before", "after"],
                required=True,
            ),
        ),
        required_one_of=[
            (
                "dns_servers",
                "search_domains",
            ),
        ],
    )

    try:
        client = Client(
            host=module.params["cluster_instance"]["host"],
            username=module.params["cluster_instance"]["username"],
            password=module.params["cluster_instance"]["password"],
        )
        rest_client = RestClient(client)
        changed, new_state, diff = run(module, rest_client)
        module.exit_json(changed=changed, new_state=new_state, diff=diff)
    except errors.ScaleComputingError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()