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

import contextlib
import os

from ironic_python_agent import errors
from ironic_python_agent.imaging import base
from ironic_python_agent.openstack.common import log
from ironic_python_agent.openstack.common import processutils
from ironic_python_agent import utils

LOG = log.getLogger(__name__)

VHD_UTIL = "/mnt/vhd-util/1.0/vhd-util"


@contextlib.contextmanager
def _temporary_chdir(path):
    old_path = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_path)


class VHDUtilImageManager(base.BaseImageManager):
    @staticmethod
    def _exec_untar(location, tar_dir):
        command = ['tar', '-C', tar_dir, '-xSf', location]
        try:
            stdout, stderr = utils.execute(*command, check_exit_code=[0])
        except processutils.ProcessExecutionError as e:
            details = ("Image at %(location)s could not be untarred: "
                       "%(stderr)s" % {'location': location,
                                       'stderr': e.stderr})
            LOG.error(details)
            raise errors.ImageFormatError(details)

    @contextlib.contextmanager
    def _untar_image(self, image_info):
        # FIXME(comstud): Instead of using '_download_image', I'd prefer
        # to use '_fetch_image' with a callback that would allow us to
        # pipe the results into an untar. Not having to write the tar
        # file to disk leaves more space for the untarred images.
        # Unfortunately oslo's processutils doesn't contain an execute()
        # method that allows data to be dynamically piped into stdin
        # of a child process.
        with self._download_image(image_info) as location:
            tar_dir = location + '.tardir'
            # Make sure this does not exist first.
            self._safe_remove_path(tar_dir)
            os.mkdir(tar_dir)
            try:
                self._exec_untar(location, tar_dir)
                yield tar_dir
            finally:
                self._safe_remove_path(tar_dir)

    def _get_vhds(self):
        """Get list of VHDs from the OVF package.

        This method assumes that the single OVF directory is the current
        working directory.

        OpenStack looks for VHDs named in 2 different ways:

        1) A single 'image.vhd'
        2) VHDs numbered in order starting with 0, like '0.vhd', '1.vhd', etc.

        #2 means that they will need to be chained before we right (they were
        generated from a snapshot).

        This method simply returns the list of VHDs in the order that they
        would need to be chained.
        """
        if os.path.exists('image.vhd'):
            return ['image.vhd']
        files = []
        i = 0
        while True:
            fname = '%s.vhd' % i
            if not os.path.exists(fname):
                break
            files.append(fname)
            i += 1
        if files:
            return files
        details = "Image does not contain image.vhd or 0.vhd files"
        raise errors.ImageFormatError(details)

    def _link_vhds(self, vhds):
        # Re-link VHDs, in reverse order, from base-copy -> leaf
        parent_path = None
        for vhd_path in reversed(vhds):
            if parent_path is None:
                parent_path = vhd_path
                continue
            # Link to parent
            command = [VHD_UTIL, "modify", "-n", vhd_path, "-p", parent_path]
            parent_path = vhd_path
            try:
                stdout, stderr = utils.execute(*command, check_exit_code=[0])
            except processutils.ProcessExecutionError as e:
                details = ("Error re-chaining VHDs: %(stdout)s / %(stderr)s" %
                           {'stdout': e.stdout,
                            'stderr': e.stderr})
                LOG.error(details)
                raise errors.ImageFormatError(details)

    def _write_vhds(self, vhds, device):
        """Write a list of VHDs to the target device.

        If there are more than 1 VHD, we need to make sure to chain them
        in order.
        """
        self._link_vhds(vhds)
        command = [VHD_UTIL, "vhd2raw", "-d", "-b", "65536", vhds[0], device]
        try:
            stdout, stderr = utils.execute(*command, check_exit_code=[0])
        except processutils.ProcessExecutionError as e:
            msg = ("Error converting to raw: %(stdout)s / %(stderr)s" %
                   {'stdout': e.stdout,
                    'stderr': e.stderr})
            LOG.error(msg)
            raise errors.ImageWriteError(device, e.exit_code, e.stdout,
                                         e.stderr)

    def write_os_image(self, image_info, device):
        """Write VHDs from OVA package to device.

        OpenStack supports VHDs within an OVA package. An OVA package is a tar
        file (compressed or not) that contains an OVF (Open Virtualization
        Format) package. An OVF package is simply a single directory with a
        number of files. There's not full support for this in that the .ovf
        within the package is an empty file. We just need to look for .vhd
        files within this package.
        """

        # NOTE(comstud): Perhaps we should really check
        # image_info['container_format'] to see if it's an 'ovf' (tar ball).
        # If the container format is 'bare', we could skip untarring and
        # just use the downloaded image as is. But openstack currently
        # only uses 1 container format for VHDs, so this is implemented
        # to match the XenServer plugin code in nova's xenapi virt driver.
        with self._untar_image(image_info) as tar_dir:
            with _temporary_chdir(tar_dir):
                vhds = self._get_vhds()
                if not vhds:
                    raise errors.ImageFormatError("No VHDs found in image")
                self._write_vhds(vhds, device)
