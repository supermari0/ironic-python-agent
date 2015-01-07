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

from ironic_python_agent import errors
from ironic_python_agent.extensions import base


class RescueExtension(base.BaseAgentExtension):
    @base.async_command('prepare_rescue')
    def prepare_rescue(self, node):
        rescue_password_hash = node.get('instance_info', {}).get('rescue_password_hash', '')

        if rescue_password_hash == "":
            raise errors.InvalidContentError("Password hash must not be empty")

        new_shadow = []
        with open("/mnt/chroot/etc/shadow", "r") as f:
            shadow = f.readlines()

            for l in shadow:
                if l.startswith("rescue:"):
                    new_shadow.append("rescue:%s:::::::" % (rescue_password_hash,))
                else:
                    new_shadow.append(l)

        with open("/mnt/chroot/etc/shadow", "w") as f:
            f.writelines(new_shadow)
