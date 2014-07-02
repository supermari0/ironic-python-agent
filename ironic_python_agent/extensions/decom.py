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
    def __init__(self):
        super(DecomExtension, self).__init__()
        self.command_map['erase_hardware'] = self.erase_hardware
        self.command_map['decommission'] = self.decommission

    def get_decom_steps(self):
        """Get a list of functions to call to decommission this hardware.

        These will be defined by the hardware manager.
        """
        pass

    @base.async_command()
    def erase_hardware(self):
        return hardware.get_manager().erase_devices()

    @base.async_command()
    def decommission(self, driver_info):
        return hardware.get_manager().decommission(driver_info)
