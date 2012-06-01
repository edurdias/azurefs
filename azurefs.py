import logging
from sys import argv, exit
from stat import S_IFDIR, S_IFREG
from errno import ENOENT, ENOSYS
from os import getuid
import time
from datetime import datetime

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from winazurestorage import *

if __name__ == '__main__':
    log = logging.getLogger()
    ch = logging.StreamHandler()
    log.addHandler(ch)
    log.setLevel(logging.DEBUG)


class AzureFS(LoggingMixIn, Operations):
    'Azure Blob Storage filesystem'

    blobs = None

    dirs = {} 
    files = {} #key: dirname
    
    def __init__(self, account, key):
        self.blobs = BlobStorage(CLOUD_BLOB_HOST, account, key)
        now = time.time()
        uid = getuid()

        self._refresh_dirs()

    def _fetch_containers(self):
        r = {} 
        for c in self.blobs.list_containers():
            r['/'+c[0]] = dict(st_mode = (S_IFDIR | 0755), st_uid = getuid(),
                               st_mtime = int(time.mktime(c[2])), st_size = 0,
                               st_nlink = 2)
        return r

    def _refresh_dirs(self):
        self.dirs = self._fetch_containers()
        max_date = sorted([self.dirs[c]['st_mtime'] for c in self.dirs])[-1]

        self.dirs['/'] = dict(st_mode = (S_IFDIR | 0755), st_uid = getuid(),
                                 st_mtime = max_date, st_size=0 , st_nlink=2)
        return self.dirs
    
    def _parse_path(self, path): # returns </dir, file(=None)>
        if path.count('/') > 1: #file
            return path[:path.rfind('/')], path[path.rfind('/')+1:]
        else: #dir
            return path[:path[1:].rfind('/')], None

    def _get_container(self, path):
        base_container = path[1:] #/abc/def/g --> abc
        if base_container.find('/') > -1:
            base_container = base_container[:base_container.find('/')]
        return base_container

    def _list_container_blobs(self, path):
        d,f = self._parse_path(path)
        if d in self.files:
            log.debug("LISTING %s, found" % d)
            return self.files[d]

        c = self._get_container(path)
        log.info("LISTING %s, CONTAINER %s, PATH %s" % (d,c, path))
        
        blobs = self.blobs.list_blobs(c)

        l = dict()
        for f in blobs:
            l[f[0]] = dict(st_mode=(S_IFREG | 0755), st_size=f[3],
                           st_mtime=int(time.mktime(f[2])), st_uid=getuid())


        self.files[d] = l
        return l

    # FUSE
    def mkdir(self, path, mode):
        log.info('Create directory %s' % path)
        d = dict(st_mode = (S_IFDIR | mode), st_nlink = 2, st_size = 0)
                 #st_ctime = time(), st_mtime = time(), st_atime = time())
        self.dirs[path] = d
        #TODO refresh containers needed?
        #TODO PUT container

    def getattr(self, path, fh=None):
        d,f = self._parse_path(path)

        if f is None: # dir
            if path not in self.dirs:
                raise FuseOSError(ENOENT)
            return self.dirs[path]
        else:
            blobs = self._list_container_blobs(path)
            if f not in blobs:
                raise FuseOSError(ENOSYS)
            else:
                return blobs[f]
    
    def getxattr(self, path, name, position=0):
        return ''

    def readdir(self, path, fh):
        if path == '/':
            return  ['.', '..'] + [(x[1:]) for x in self.dirs if x != '/']
        else:
            blobs = self._list_container_blobs(path)
            return ['.', '..'] + blobs.keys()

    def chown(self, path, uid, gid): pass
    def chmod(self, path, mode): pass

if __name__ == '__main__':
    if len(argv) < 4:
        print('Usage: %s <mount_directory> <account> <secret_key>' % argv[0])
        exit(1)
    fuse = FUSE(AzureFS(argv[2], argv[3]), argv[1], debug=True)

