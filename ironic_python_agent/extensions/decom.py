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

from ironic_python_agent.extensions import base
from ironic_python_agent import hardware


class DecomExtension(base.BaseAgentExtension):
    @base.async_command('erase_hardware')
    def erase_hardware(self):
        return hardware.get_manager().erase_devices()

    @base.async_command('get_decommission_steps')
    def get_decommission_steps(self):
        # Results should be a dict, not a list
        manager = hardware.get_manager()
        return {
            'decommission_steps': manager.get_decommission_steps(),
        }

    @base.async_command('decommission')
    def decommission(self, node, ports, **kwargs):
        return hardware.get_manager().decommission(node, ports, **kwargs)
