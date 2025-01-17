# -*- coding: utf-8 -*-
# Copyright: (c) 2023, XLAB Steampunk <steampunk@xlab.si>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
from __future__ import annotations

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ..module_utils.typed_classes import (
    TypedVirtualDiskFromAnsible,
    TypedVirtualDiskToAnsible,
    TypedTaskTag,
)
from typing import Dict, List, Any, Optional

from .rest_client import RestClient
from ..module_utils.utils import PayloadMapper
from ..module_utils import errors

REQUEST_TIMEOUT_TIME = 3600


class VirtualDisk(PayloadMapper):
    def __init__(
        self,
        name: Optional[str] = None,
        uuid: Optional[str] = None,
        block_size: Optional[int] = None,
        size: Optional[int] = None,
        # allocated_size: int = None,
        replication_factor: Optional[int] = None,
    ):
        self.name = name
        self.uuid = uuid
        self.block_size = block_size
        self.size = size
        # self.allocated_size = allocated_size
        self.replication_factor = replication_factor

    @classmethod
    def from_ansible(cls, ansible_data: TypedVirtualDiskFromAnsible) -> VirtualDisk:
        return cls(
            name=ansible_data["name"],
        )

    @classmethod
    def from_hypercore(cls, hypercore_data: Dict[Any, Any]) -> VirtualDisk:
        try:
            return cls(
                name=hypercore_data["name"],
                uuid=hypercore_data["uuid"],
                block_size=hypercore_data["blockSize"],
                size=hypercore_data["capacityBytes"],
                # allocated_size=hypercore_data["totalAllocationBytes"],
                replication_factor=hypercore_data["replicationFactor"],
            )
        except KeyError as e:
            raise errors.MissingValueHypercore(e)

    def to_hypercore(self) -> Dict[Any, Any]:
        raise NotImplementedError()

    def to_ansible(self) -> TypedVirtualDiskToAnsible:
        return dict(
            name=self.name,
            uuid=self.uuid,
            block_size=self.block_size,
            size=self.size,
            # allocated_size=self.allocated_size,
            replication_factor=self.replication_factor,
        )

    # This method is here for testing purposes!
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VirtualDisk):
            return NotImplemented
        return all(
            (
                self.uuid == other.uuid,
                self.name == other.name,
                self.block_size == other.block_size,
                self.size == other.size,
                # self.allocated_size == other.allocated_size,
                self.replication_factor == other.replication_factor,
            )
        )

    # @classmethod
    # def get_by_uuid(cls, ansible_dict, rest_client, must_exist=False):
    #     query = get_query(ansible_dict, "uuid", ansible_hypercore_map=dict(uuid="uuid"))
    #     hypercore_dict = rest_client.get_record(
    #         "/rest/v1/VirtualDisk", query, must_exist=must_exist
    #     )
    #     virtual_disk = VirtualDisk.from_hypercore(hypercore_dict)
    #     return virtual_disk

    @classmethod
    def get_by_name(
        cls, rest_client: RestClient, name: str, must_exist: bool = False
    ) -> Optional[VirtualDisk]:
        result = rest_client.list_records("/rest/v1/VirtualDisk", query=dict(name=name))
        if not isinstance(result, list):
            raise errors.ScaleComputingError(
                "Virtual disk API return value is not a list."
            )
        elif must_exist and (not result or not result[0]):
            raise errors.ScaleComputingError(
                f"Virtual disk with name {name} does not exist."
            )
        elif not result or not result[0]:
            return None
        elif len(result) > 1:
            raise errors.ScaleComputingError(
                f"Virtual disk {name} has multiple instances and is not unique."
            )
        return cls.from_hypercore(result[0])

    @classmethod
    def get_state(
        cls, rest_client: RestClient, query: Dict[Any, Any]
    ) -> List[TypedVirtualDiskToAnsible]:
        state = [
            cls.from_hypercore(hypercore_data=hypercore_dict).to_ansible()
            for hypercore_dict in rest_client.list_records(
                "/rest/v1/VirtualDisk", query
            )
        ]
        return state

    # Uploads a disk file (qcow2, vmdk, vhd); Hypercore creates virtual disk from uploaded file.
    # Filename and filesize need to be send as parameters in PUT request.
    @staticmethod
    def send_upload_request(
        rest_client: RestClient, file_size: int, module: AnsibleModule
    ) -> TypedTaskTag:
        if (
            file_size is None
            or not module.params["name"]
            or not module.params["source"]
        ):
            raise errors.ScaleComputingError(
                "Missing some virtual disk file values inside upload request."
            )
        try:
            with open(module.params["source"], "rb") as source_file:
                task = rest_client.put_record(
                    endpoint="/rest/v1/VirtualDisk/upload",
                    payload=None,
                    check_mode=False,
                    query=dict(filename=module.params["name"], filesize=file_size),
                    timeout=REQUEST_TIMEOUT_TIME,
                    binary_data=source_file,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Accept": "application/json",
                        "Content-Length": file_size,
                    },
                )
        except FileNotFoundError:
            raise errors.ScaleComputingError(
                f"Disk file {module.params['source']} not found."
            )
        return task

    def send_delete_request(self, rest_client: RestClient) -> TypedTaskTag:
        if not self.uuid:
            raise errors.ScaleComputingError(
                "Missing virtual disk UUID inside delete request."
            )
        return rest_client.delete_record(
            f"/rest/v1/VirtualDisk/{self.uuid}", check_mode=False
        )
