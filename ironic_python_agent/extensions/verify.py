# Copyright 2014 Rackspace, Inc.
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


class VerifyExtension(base.BaseAgentExtension):
    def __init__(self):
        super(VerifyExtension, self).__init__()
        self.command_map['verify_hardware'] = self.verify_hardware

    @base.async_command()
    def verify_hardware(self, properties, ports, extra=None):
        """Given data about a node, attempt to verify the data is correct.

        :param properties: all or a subset of node.properties
        :param ports: a dict representation of Ports connected to the node
        :param extra: an extra dictionary, for vendor specific data
        :raises VerificationException: if any of the steps determine the node
                does not match the given data
        :raises VerificationStepDoesNotExist: if a given step isn't a function
                of the hardware manager
        :return: The output of each verification step, as listed in
                 HardwareManager.get_verification_steps()
        """
        return hardware.get_manager().verify_hardware(properties, ports, extra)
