# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import crypt
import random
import string

from oslo_log import log

from ironic_python_agent.extensions import base

LOG = log.getLogger()


class RescueExtension(base.BaseAgentExtension):

    def make_salt(self):
        """Generate a random salt for hashing the rescue password.

           Salt should be a two-character string from the set [a-zA-Z0-9].

           :returns: a valid salt for use with crypt.crypt"""
        allowed_chars = ''.join([string.ascii_letters, string.digits])
        return ''.join(random.choice(allowed_chars) for i in range(2))

    def write_rescue_password(self, rescue_password):
        """Write rescue password to a file for use after IPA exits."""
        # TODO(mariojv) Need to make sure /etc or whatever dir we use is
        # available outside of container
        pass_file = '/etc/ipa_rescue_password'
        LOG.debug('Writing hashed rescue password to %s', pass_file)
        salt = self.make_salt()
        hashed_password = crypt.crypt(rescue_password, salt)
        with open(pass_file, 'w') as f:
            f.write(hashed_password)

    def write_configdrive(self, configdrive):
        """b64decode configdrive and write it to a file.

           The configdrive gzip file must be gunzipped and mounted to the
           appropriate location later.
           TODO(mariojv) What do we actually do with the configdrive + glean? ^
        """
        configdrive_file = '/etc/ipa_rescue_configdrive'
        LOG.debug('Decoding configdrive and writing to %s', configdrive_file)
        decoded_cfgdrive = base64.b64decode(configdrive)
        with open(configdrive_file, 'w') as f:
            f.write(decoded_cfgdrive)

    @base.sync_command('finalize_rescue')
    def finalize_rescue(self, rescue_password, configdrive):
        self.write_rescue_password(rescue_password)
        self.write_configdrive(configdrive)
        # IPA will terminate after the result of finalize_rescue is returned to
        # ironic to avoid exposing the IPA API to a tenant or public network
        self.agent.serve_api = False
        return
