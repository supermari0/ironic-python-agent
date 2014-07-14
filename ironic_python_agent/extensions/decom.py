# Copyright 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ironic_python_agent import errors
from ironic_python_agent.extensions import base
from ironic_python_agent import hardware


class DecomExtension(base.BaseAgentExtension):
    @base.async_command('erase_hardware')
    def erase_hardware(self):
        return hardware.get_manager().erase_devices()

    @base.async_command('get_hardware_manager_version')
    def get_hardware_manager_version(self):
        manager = hardware.get_manager()
        return {
            'hardware_manager_version': manager.HARDWARE_MANAGER_VERSION
        }

    @base.async_command('get_decommission_steps')
    def get_decommission_steps(self):
        # Results should be a dict, not a list
        manager = hardware.get_manager()
        return {
            'decommission_steps': manager.get_decommission_steps(),
        }

    @base.async_command('decommission')
    def decommission(self, node=None, ports=None, driver_info=None, **kwargs):
        if not ports:
            ports = []

        # Current way
        if node and not driver_info:
            return hardware.get_manager().decommission(node, ports, **kwargs)
        # Backwards compatibility
        elif driver_info and not node:
            node = {'driver_info': driver_info}
            return hardware.get_manager().decommission(node, [], **kwargs)
        else:
            raise errors.InvalidContentError(
                'Either provide "node" and "ports" params, or "driver_info".')
