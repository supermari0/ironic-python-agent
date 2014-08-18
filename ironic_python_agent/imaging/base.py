# Copyright 2013-2014 Rackspace, Inc.
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

import base64
import contextlib
import gzip
import md5
import os
import requests
import shutil
import StringIO
import time

from ironic_python_agent import errors
from ironic_python_agent.openstack.common import log
from ironic_python_agent.openstack.common import processutils
from ironic_python_agent import utils

LOG = log.getLogger(__name__)


class BaseImageManager(object):
    def __init__(self, tmpdir=None):
        if tmpdir is None:
            tmpdir = '/tmp'
        self.tmpdir = tmpdir

    def _image_location(self, image_info):
        return os.path.join(self.tmpdir, image_info['id'])

    def _configdrive_location(self):
        return os.path.join(self.tmpdir, 'configdrive')

    @staticmethod
    def _path_to_script(script):
        cwd = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(cwd, '..', script)

    @staticmethod
    def _request_url(image_info, url):
        resp = requests.get(url, stream=True)
        if resp.status_code != 200:
            reason = 'Got HTTP status code of %s' % resp.status_code
            raise errors.ImageDownloadError(image_info['id'], reason)
        return resp

    def _fetch_image(self, image_info, read_cb):
        image_id = image_info['id']

        if not image_info['urls']:
            raise errors.ImageDownloadError(image_id, 'No URLs provided')

        for url in image_info['urls']:
            starttime = time.time()
            LOG.info('Attempting to fetch image %(id)s from %(url)s',
                     {'id': image_id, 'url': url})
            try:
                resp = self._request_url(image_info, url)
                break
            except errors.ImageDownloadError as e:
                last_error = e
                LOG.warning('Image %(id)s failed to download from '
                            '%(url)s: %(reason)s',
                            {'id': image_id,
                             'url': url,
                             'reason': e.reason})
        else:
            raise errors.ImageDownloadError(image_id, last_error.reason)

        checksum = md5.new()
        try:
            for chunk in resp.iter_content(1024 * 1024):
                checksum.update(chunk)
                read_cb(chunk)
        except Exception as e:
            raise errors.ImageDownloadError(image_info['id'],
                                            str(e))

        checksum = checksum.hexdigest()
        totaltime = time.time() - starttime
        LOG.info('Image %(id)s downloaded in %(time)s second(s)',
                 {'id': image_id, 'time': totaltime})

        if checksum != image_info['checksum']:
            LOG.error('MD5 Checksum mismatch detected for image '
                      '%(id)s: remote: %(rem)s, local: %(loc)s',
                      {'id': image_id,
                       'rem': image_info['checksum'],
                       'loc': checksum})
            raise errors.ImageChecksumError(image_id)

    @contextlib.contextmanager
    def _download_image(self, image_info):
        location = self._image_location(image_info)
        try:
            with open(location, 'w') as f:
                self._fetch_image(image_info, f.write)
            yield location
        finally:
            self._safe_remove_path(location)

    @staticmethod
    def _safe_remove_path(path):
        shutil.rmtree(path, ignore_errors=True)

    @contextlib.contextmanager
    def _unpack_configdrive(self, configdrive):
        location = self._configdrive_location()
        LOG.debug('Writing configdrive to %(loc)s', {'loc': location})
        # configdrive data is base64'd, decode it first
        data = StringIO.StringIO(base64.b64decode(configdrive))
        gunzipped = gzip.GzipFile('configdrive', 'rb', 9, data)
        try:
            with open(location, 'wb') as f:
                f.write(gunzipped.read())
            gunzipped.close()
            gunzipped = None
            # check configdrive size before writing it
            filesize = os.stat(location).st_size
            if filesize > (64 * 1024 * 1024):
                raise errors.ConfigDriveTooLargeError(location, filesize)
            yield location
        finally:
            self._safe_remove_path(location)
            if gunzipped is not None:
                gunzipped.close()

    def write_os_image(self, image_info, device):
        """Download image and write it to a device."""
        pass

    def write_configdrive(self, configdrive, device):
        with self._unpack_configdrive(configdrive) as location:
            script = self._path_to_script('shell/copy_configdrive_to_disk.sh')
            command = ['/bin/bash', script, location, device]
            LOG.info('Copying configdrive to disk with command %(cmd)s',
                     {'cmd': ' '.join(command)})
            try:
                stdout, stderr = utils.execute(*command, check_exit_code=[0])
            except processutils.ProcessExecutionError as e:
                raise errors.ConfigDriveWriteError(device,
                                                   e.exit_code,
                                                   e.stdout,
                                                   e.stderr)
