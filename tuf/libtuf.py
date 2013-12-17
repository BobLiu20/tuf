"""
<Program Name>
  libtuf.py

<Author>
  Vladimir Diaz <vladimir.v.diaz@gmail.com>

<Started>
  October 19, 2013 

<Copyright>
  See LICENSE for licensing information.

<Purpose>
  See 'tuf.README' for a complete guide on using 'tuf.libtuf.py'.
"""

# Help with Python 3 compatibility, where the print statement is a function, an
# implicit relative import is invalid, and the '/' operator performs true
# division.  Example:  print 'hello world' raises a 'SyntaxError' exception.
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import os
import errno
import sys
import time
import getpass
import logging
import tempfile
import shutil
import json
import gzip

import tuf
import tuf.formats
import tuf.util
import tuf.keydb
import tuf.roledb
import tuf.keys
import tuf.sig
import tuf.log


# See 'log.py' to learn how logging is handled in TUF.
logger = logging.getLogger('tuf.libtuf')

# Recommended RSA key sizes:
# http://www.emc.com/emc-plus/rsa-labs/historical/twirl-and-rsa-key-size.htm#table1 
# According to the document above, revised May 6, 2003, RSA keys of
# size 3072 provide security through 2031 and beyond.  2048-bit keys
# are the recommended minimum and are good from the present through 2030.
DEFAULT_RSA_KEY_BITS = 3072

# The metadata filenames of the top-level roles.
ROOT_FILENAME = 'root.txt'
TARGETS_FILENAME = 'targets.txt'
RELEASE_FILENAME = 'release.txt'
TIMESTAMP_FILENAME = 'timestamp.txt'

# The targets and metadata directory names.
METADATA_STAGED_DIRECTORY_NAME = 'metadata.staged'
METADATA_DIRECTORY_NAME = 'metadata'
TARGETS_DIRECTORY_NAME = 'targets' 

# The supported file extensions of TUF metadata files.
METADATA_EXTENSION = '.txt'
METADATA_EXTENSIONS = ['.txt', '.txt.gz']

# The recognized compression extensions. 
SUPPORTED_COMPRESSION_EXTENSIONS = ['.gz']

# Supported key types.
SUPPORTED_KEY_TYPES = ['rsa', 'ed25519']

# Expiration date delta, in seconds, of the top-level roles.  A metadata
# expiration date is set by taking the current time and adding the expiration
# seconds listed below.

# Initial 'root.txt' expiration time of 1 year. 
ROOT_EXPIRATION = 31556900

# Initial 'targets.txt' expiration time of 3 months. 
TARGETS_EXPIRATION = 7889230 

# Initial 'release.txt' expiration time of 1 week. 
RELEASE_EXPIRATION = 604800 

# Initial 'timestamp.txt' expiration time of 1 day.
TIMESTAMP_EXPIRATION = 86400

# The suffix added to metadata filenames of partially written metadata.
# Partial metadata may contain insufficient number of signatures and require
# multiple repository maintainers to independently sign them.
#PARTIAL_METADATA_SUFFIX = '.partial'


class Repository(object):
  """
  <Purpose>
  
  <Arguments>
    repository_directory:

    metadata_directory:

    targets_directory:

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

  <Side Effects>

  <Returns>
    Repository object.
  """
 
  def __init__(self, repository_directory, metadata_directory, targets_directory):
  
    # Do the arguments have the correct format?
    # Raise 'tuf.FormatError' if any of the arguments are improperly formatted.
    tuf.formats.PATH_SCHEMA.check_match(repository_directory)
    tuf.formats.PATH_SCHEMA.check_match(metadata_directory)
    tuf.formats.PATH_SCHEMA.check_match(targets_directory)
    
    self._repository_directory = repository_directory
    self._metadata_directory = metadata_directory
    self._targets_directory = targets_directory
   
    # Set the top-level role objects.
    self.root = Root() 
    self.release = Release()
    self.timestamp = Timestamp()
    self.targets = Targets(self._targets_directory, 'targets')



  def write(self, write_partial=False):
    """
    <Purpose>
      Write all the JSON Metadata objects to their corresponding files.  
    
    <Arguments>
      write_partial:
        
    <Exceptions>
      tuf.RepositoryError, if any of the top-level roles do not have a minimum
      threshold of signatures.

    <Side Effects>
      Creates metadata files in the repository's metadata directory.

    <Returns>
      None.
    """
    
    # Does 'partial' have the correct format?
    # Ensure the arguments have the appropriate number of objects and object
    # types, and that all dict keys are properly named.
    # Raise 'tuf.FormatError' if 'partial' is improperly formatted.
    tuf.formats.BOOLEAN_SCHEMA.check_match(write_partial)
    
    # At this point the tuf.keydb and tuf.roledb stores must be fully
    # populated, otherwise write() throwns a 'tuf.Repository' exception if 
    # any of the top-level roles are missing signatures, keys, etc.
    filenames = get_metadata_filenames(self._metadata_directory)
    root_filename = filenames[ROOT_FILENAME] 
    targets_filename = filenames[TARGETS_FILENAME] 
    release_filename = filenames[RELEASE_FILENAME] 
    timestamp_filename = filenames[TIMESTAMP_FILENAME] 

    # Write the metadata files of all the delegated roles.
    delegated_roles = tuf.roledb.get_delegated_rolenames('targets')
    for delegated_role in delegated_roles:
      roleinfo = tuf.roledb.get_roleinfo(delegated_role)
      
      write_delegated_metadata_file(self._repository_directory,
                                    self._targets_directory, 
                                    delegated_role, roleinfo, write_partial)

    # Generate the 'root.txt' metadata file.
    # _generate_and_write_metadata() raises a 'tuf.Error' exception if the
    # metadata cannot be written.
    _generate_and_write_metadata('root', filenames, write_partial,
                                 self._targets_directory,
                                 self._metadata_directory)
    
    # Generate the 'targets.txt' metadata file.
    _generate_and_write_metadata('targets', filenames, write_partial,
                                 self._targets_directory,
                                 self._metadata_directory)
    
    # Generate the 'release.txt' metadata file.
    _generate_and_write_metadata('release', filenames, write_partial,
                                 self._targets_directory,
                                 self._metadata_directory)
    
    # Generate the 'timestamp.txt' metadata file.
    _generate_and_write_metadata('timestamp', filenames, write_partial,
                                 self._targets_directory,
                                 self._metadata_directory)
     
    # Delete the metadata of roles no longer in 'tuf.roledb'.  Obsolete roles
    # may have been revoked.
    _delete_obsolete_metadata(self._metadata_directory)


  
  def write_partial(self):
    """
    <Purpose>
      Write all the JSON Metadata objects to their corresponding files, but
      allow metadata files to contain an invalid threshold of signatures.  
    
    <Arguments>
      None.

    <Exceptions>
      tuf.RepositoryError, if any of the top-level roles do not have a minimum
      threshold of signatures.

    <Side Effects>
      Creates metadata files in the repository's metadata directory.

    <Returns>
      None.
    """

    self.write(write_partial=True)
  
  
  
  def status(self):
    """
    <Purpose>
    
    <Arguments>
      None.

    <Exceptions>

    <Side Effects>

    <Returns>
      None.
    """
   
    temp_repository_directory = None

    try:
      temp_repository_directory = tempfile.mkdtemp()
      metadata_directory = os.path.join(temp_repository_directory,
                                        METADATA_STAGED_DIRECTORY_NAME)
      os.mkdir(metadata_directory)

      filenames = get_metadata_filenames(metadata_directory)
    
      # Delegated roles.
      delegated_roles = tuf.roledb.get_delegated_rolenames('targets')
      insufficient_keys = []
      insufficient_signatures = []
      
      for delegated_role in delegated_roles:
        try: 
          _check_role_keys(delegated_role)
        except tuf.InsufficientKeysError, e:
          insufficient_keys.append(delegated_role)
          continue
        
        roleinfo = tuf.roledb.get_roleinfo(delegated_role)
        try: 
          write_delegated_metadata_file(temp_repository_directory,
                                        self._targets_directory,
                                        delegated_role, roleinfo,
                                        write_partial=False)
        except tuf.Error, e:
          insufficient_signatures.append(delegated_role)
      
      if len(insufficient_keys):
        message = 'Delegated roles with insufficient keys: '+ \
          repr(insufficient_keys)
        print(message)
        return

      if len(insufficient_signatures):
        message = 'Delegated roles with insufficient signatures: '+ \
          repr(insufficient_signatures)
        print(message) 
        return

      # Root role.
      try: 
        _check_role_keys(self.root.rolename)
      except tuf.InsufficientKeysError, e:
        print(str(e))
        return

      try:
       signable =  _generate_and_write_metadata(self.root.rolename,
                                                filenames, False,
                                                self._targets_directory,
                                                metadata_directory)
       _print_status(self.root.rolename, signable)
      except tuf.Error, e:
        signable = e[1]
        _print_status(self.root.rolename, signable)
        return

      # Targets role.
      try: 
        _check_role_keys(self.targets.rolename)
      except tuf.InsufficientKeysError, e:
        print(str(e))
        return
      
      try:
       signable =  _generate_and_write_metadata(self.targets.rolename,
                                                filenames, False,
                                                self._targets_directory,
                                                metadata_directory)
       _print_status(self.targets.rolename, signable)
      except tuf.Error, e:
        signable = e[1]
        _print_status(self.targets.rolename, signable)
        return

      # Release role.
      try:
        _check_role_keys(self.release.rolename)
      except tuf.InsufficientKeysError, e:
        print(str(e))
        return
      
      try:
       signable =  _generate_and_write_metadata(self.release.rolename,
                                                filenames, False,
                                                self._targets_directory,
                                                metadata_directory)
       _print_status(self.release.rolename, signable)
      except tuf.Error, e:
        signable = e[1]
        _print_status(self.release.rolename, signable)
        return
      
      # Timestamp role.
      try:
        _check_role_keys(self.timestamp.rolename)
      except tuf.InsufficientKeysError, e:
        print(str(e))
        return
      
      try:
       signable =  _generate_and_write_metadata(self.timestamp.rolename,
                                                filenames, False,
                                                self._targets_directory,
                                                metadata_directory)
       _print_status(self.timestamp.rolename, signable)
      except tuf.Error, e:
        signable = e[1]
        _print_status(self.timestamp.rolename, signable)
        return
    
    finally:
      shutil.rmtree(temp_repository_directory, ignore_errors=True)



  def get_filepaths_in_directory(self, files_directory, recursive_walk=False,
                                 followlinks=True):
    """
    <Purpose>
      Walk the given files_directory to build a list of target files in it.

    <Arguments>
      files_directory:
        The path to a directory of target files.

      recursive_walk:
        To recursively walk the directory, set recursive_walk=True.

      followlinks:
        To follow symbolic links, set followlinks=True.

    <Exceptions>
      tuf.FormatError, if the arguments are improperly formatted.

      tuf.Error, if 
      Python IO exceptions.

    <Side Effects>
      None.

    <Returns>
      A list of absolute paths to target files in the given files_directory.
    """

    # Do the arguments have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.PATH_SCHEMA.check_match(files_directory)
    tuf.formats.BOOLEAN_SCHEMA.check_match(recursive_walk)
    tuf.formats.BOOLEAN_SCHEMA.check_match(followlinks)

    if not os.path.isdir(files_directory):
      message = repr(files_directory)+' is not a directory.'
      raise tuf.Error(message)
    
    targets = []

    # FIXME: We need a way to tell Python 2, but not Python 3, to return
    # filenames in Unicode; see #61 and:
    # http://docs.python.org/2/howto/unicode.html#unicode-filenames
    for dirpath, dirnames, filenames in os.walk(files_directory,
                                                followlinks=followlinks):
      for filename in filenames:
        full_target_path = os.path.join(dirpath, filename)
        targets.append(full_target_path)

      # Prune the subdirectories to walk right now if we do not wish to
      # recursively walk files_directory.
      if recursive_walk is False:
        del dirnames[:]

    return targets





class Metadata(object):
  """
  <Purpose>
    Write all the Metadata objects' JSON contents to the corresponding files. 
  
  <Arguments>

  <Exceptions>

  <Side Effects>

  <Returns>
  """

  def __init__(self):
    self._rolename = None    
    


  def add_key(self, key):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>

    <Side Effects>

    <Returns>
      None.
    """
   
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.ANYKEY_SCHEMA.check_match(key)

    try:
      tuf.keydb.add_key(key)
    except tuf.KeyAlreadyExistsError, e:
      pass
   
    keyid = key['keyid']
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if keyid not in roleinfo['keyids']: 
      roleinfo['keyids'].append(keyid)
      tuf.roledb.update_roleinfo(self._rolename, roleinfo)
   


  def remove_key(self, key):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>
      tuf.FormatError, if 'key' is improperly formatted.

    <Side Effects>
      Updates 'tuf.keydb.py'.

    <Returns>
      None.
    """
    
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.ANYKEY_SCHEMA.check_match(key)
    
    keyid = key['keyid']
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if keyid in roleinfo['keyids']: 
      roleinfo['keyids'].remove(keyid)
      tuf.roledb.update_roleinfo(self._rolename, roleinfo)
   


  def load_signing_key(self, key):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>
      tuf.FormatError, if 'key' is improperly formatted.

      tuf.Error, if the private key is unavailable in 'key'.

    <Side Effects>
      Updates 'tuf.keydb.py'.

    <Returns>
      None.
    """
    
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.ANYKEY_SCHEMA.check_match(key)
   
    if not len(key['keyval']['private']):
      message = 'The private key is unavailable.'
      raise tuf.Error(message)

    try:
      tuf.keydb.add_key(key)
    except tuf.KeyAlreadyExistsError, e:
      tuf.keydb.remove_key(key['keyid'])
      tuf.keydb.add_key(key)

    # Update 'signing_keys' in roledb.
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if key['keyid'] not in roleinfo['signing_keyids']:
      roleinfo['signing_keyids'].append(key['keyid'])
      tuf.roledb.update_roleinfo(self.rolename, roleinfo)
  
  
  
  def unload_signing_key(self, key):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>
      tuf.FormatError, if 'key' is improperly formatted.

      tuf.Error, if the private key is unavailable in 'key'.

    <Side Effects>
      Updates 'tuf.keydb.py'.

    <Returns>
      None.
    """
    
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.ANYKEY_SCHEMA.check_match(key)
    
    # Update 'signing_keys' in roledb.
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if key['keyid'] in roleinfo['signing_keyids']:
      roleinfo['signing_keyids'].remove(key['keyid'])
      tuf.roledb.update_roleinfo(self.rolename, roleinfo)



  def add_signature(self, signature):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>
      tuf.FormatError, if 'key' is improperly formatted.

      tuf.Error, if the private key is unavailable in 'key'.

    <Side Effects>
      Updates 'tuf.keydb.py'.

    <Returns>
      None.
    """
    
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.SIGNATURE_SCHEMA.check_match(signature)
  
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if 'signatures' not in roleinfo:
      roleinfo['signatures'] = []
    
    if signature not in roleinfo['signatures']:
      roleinfo['signatures'].append(signature)
      tuf.roledb.update_roleinfo(self.rolename, roleinfo)



  def remove_signature(self, signature):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      key:
        tuf.formats.ANYKEY_SCHEMA

    <Exceptions>
      tuf.FormatError, if 'key' is improperly formatted.

      tuf.Error, if the private key is unavailable in 'key'.

    <Side Effects>
      Updates 'tuf.keydb.py'.

    <Returns>
      None.
    """
    
    # Does 'key' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.SIGNATURE_SCHEMA.check_match(signature)
  
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    if signature in roleinfo['signatures']:
      roleinfo['signatures'].remove(signature)
      tuf.roledb.update_roleinfo(self.rolename, roleinfo)



  @property
  def signatures(self):
    """
    """

    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    signatures = roleinfo['signatures']
  
    return signatures



  @property
  def keys(self):
    """
    """

    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    keyids = roleinfo['keyids']

    return keyids



  @property
  def rolename(self):
    """
    """

    return self._rolename
  
  
  
  @property
  def version(self):
    """
    """
    
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    version = roleinfo['version'] 

    return version
  
  
  
  @version.setter
  def version(self, version):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      threshold:
        tuf.formats.THRESHOLD_SCHEMA

    <Exceptions>
      tuf.FormatError, if the argument is improperly formatted.

    <Side Effects>
      Modifies the threshold attribute of the Repository object.

    <Returns>
      None.
    """
    
    # Does 'version' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.METADATAVERSION_SCHEMA.check_match(version)
    
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    roleinfo['version'] = version 
    
    tuf.roledb.update_roleinfo(self._rolename, roleinfo)



  @property
  def threshold(self):
    """
    """
    
    roleinfo = tuf.roledb.get_roleinfo(self._rolename)
    threshold = roleinfo['threshold']

    return threshold



  @threshold.setter 
  def threshold(self, threshold):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      threshold:
        tuf.formats.THRESHOLD_SCHEMA

    <Exceptions>
      tuf.FormatError, if the argument is improperly formatted.

    <Side Effects>
      Modifies the threshold attribute of the Repository object.

    <Returns>
      None.
    """
   
    # Does 'threshold' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.THRESHOLD_SCHEMA.check_match(threshold)
    
    roleinfo = tuf.roledb.get_roleinfo(self._rolename)
    roleinfo['threshold'] = threshold
    
    tuf.roledb.update_roleinfo(self._rolename, roleinfo)
    self._threshold = threshold
 

  @property
  def expiration(self):
    """
    <Purpose>

      >>> 
      >>> 
      >>> 

    <Arguments>
      None.
    
    <Exceptions>
      None.

    <Side Effects>
      None.

    <Returns>
      The role's expiration datetime, conformant to tuf.formats.DATETIME_SCHEMA.
    """
    
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)

    return roleinfo['expires']



  @expiration.setter
  def expiration(self, expiration_datetime_utc):
    """
    <Purpose>
      TODO: expiration_datetime_utc in ISO 8601 format.
      
      >>>  
      >>> 
      >>> 

    <Arguments>
      expiration_datetime_utc:
        tuf.formats.DATETIME_SCHEMA

    <Exceptions>
      tuf.FormatError, if the argument is improperly formatted.
    
    <Side Effects>
      Modifies the expiration attribute of the Repository object.

    <Returns>
      None.
    """
    
    # Does 'expiration_datetime_utc' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.DATETIME_SCHEMA.check_match(expiration_datetime_utc)
   
    expiration_datetime_utc = expiration_datetime_utc+' UTC'
    try:
      unix_timestamp = tuf.formats.parse_time(expiration_datetime_utc)
    except (tuf.FormatError, ValueError), e:
      message = 'Invalid datetime argument: '+repr(expiration_datetime_utc)
      raise tuf.FormatError(message)
    
    if unix_timestamp < time.time():
      message = 'The expiration date must occur after the current date.'
      raise tuf.FormatError(message)
    
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    roleinfo['expires'] = expiration_datetime_utc
    tuf.roledb.update_roleinfo(self.rolename, roleinfo)
  
  
  
  @property
  def signing_keys(self):
    """
    """

    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    signing_keyids = roleinfo['signing_keyids']

    return signing_keyids



  @property
  def compressions(self):
    """
    """

    tuf.roledb.get_roleinfo(self.rolename)
    compressions = roleinfo['compressions']

    return compressions



  @compressions.setter
  def compressions(self, compression_list):
    """
    """
   
    # Does 'compression_name' have the correct format?
    # Raise 'tuf.FormatError' if it is improperly formatted.
    tuf.formats.COMPRESSIONS_SCHEMA.check_match(compression_list)

    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    roleinfo['compressions'].extend(compression_list)
    tuf.roledb.update_roleinfo(self.rolename, roleinfo)





class Root(Metadata):
  """
  <Purpose>

    >>> 
    >>> 
    >>> 

  <Arguments>

  <Exceptions>

  <Side Effects>

  <Returns>
  """

  def __init__(self):
    
    super(Root, self).__init__() 
    
    self._rolename = 'root'
   
    expiration = tuf.formats.format_time(time.time()+ROOT_EXPIRATION)

    roleinfo = {'keyids': [], 'signing_keyids': [], 'threshold': 1, 
                'signatures': [], 'version': 0, 'compressions': [''],
                'expires': expiration, 'partial_loaded': False}
    try: 
      tuf.roledb.add_role(self._rolename, roleinfo)
    except tuf.RoleAlreadyExistsError, e:
      pass





class Timestamp(Metadata):
  """
  <Purpose>

    >>>
    >>>
    >>>

  <Arguments>

  <Exceptions>

  <Side Effects>

  <Returns>
  """

  def __init__(self):
    
    super(Timestamp, self).__init__() 
    
    self._rolename = 'timestamp'

    expiration = tuf.formats.format_time(time.time()+TIMESTAMP_EXPIRATION)

    roleinfo = {'keyids': [], 'signing_keyids': [], 'threshold': 1,
                'signatures': [], 'version': 0, 'compressions': [''],
                'expires': expiration, 'partial_loaded': False}
    
    try: 
      tuf.roledb.add_role(self.rolename, roleinfo)
    except tuf.RoleAlreadyExistsError, e:
      pass





class Release(Metadata):
  """
  <Purpose>

    >>> 
    >>>
    >>>

  <Arguments>

  <Exceptions>

  <Side Effects>

  <Returns>
  """

  def __init__(self):
    
    super(Release, self).__init__() 
    
    self._rolename = 'release' 
    
    expiration = tuf.formats.format_time(time.time()+RELEASE_EXPIRATION)
    
    roleinfo = {'keyids': [], 'signing_keyids': [], 'threshold': 1,
                'signatures': [], 'version': 0, 'compressions': [''],
                'expires': expiration, 'partial_loaded': False}
    
    try:
      tuf.roledb.add_role(self._rolename, roleinfo)
    except tuf.RoleAlreadyExistsError, e:
      pass





class Targets(Metadata):
  """
  <Purpose>

    >>> 
    >>>
    >>>

  <Arguments>
    targets_directory:
      The targets directory of the Repository object.

  <Exceptions>
    tuf.FormatError, if the targets directory argument is improerly formatted.

  <Side Effects>
    Mofifies the roleinfo of the targets role in 'tuf.roledb'.
  
  <Returns>
    None.
  """
  
  def __init__(self, targets_directory, rolename, roleinfo=None):
   
    # Do the arguments have the correct format?
    # Ensure the arguments have the appropriate number of objects and object
    # types, and that all dict keys are properly named.
    # Raise 'tuf.FormatError' if any are improperly formatted.
    tuf.formats.PATH_SCHEMA.check_match(targets_directory)
    tuf.formats.ROLENAME_SCHEMA.check_match(rolename)
    
    if roleinfo is not None:
      tuf.formats.ROLEDB_SCHEMA.check_match(roleinfo)

    super(Targets, self).__init__()
    self._targets_directory = targets_directory
    self._rolename = rolename 
    self._target_files = []
   
    expiration = tuf.formats.format_time(time.time()+TARGETS_EXPIRATION)

    if roleinfo is None:
      roleinfo = {'keyids': [], 'signing_keyids': [], 'threshold': 1,
                  'version': 0, 'compressions': [''], 'expires': expiration,
                  'signatures': [], 'paths': [], 'path_hash_prefixes': [],
                  'partial_loaded': False, 'delegations': {'keys': {},
                                                           'roles': []}}
    
    try:
      tuf.roledb.add_role(self.rolename, roleinfo)
    except tuf.RoleAlreadyExistsError, e:
      pass  



  @property
  def target_files(self):
    """
    <Purpose>

      >>> 
      >>>
      >>>

    <Arguments>
      targets_directory:
        The targets directory of the Repository object.

    <Exceptions>
      tuf.FormatError, if the targets directory argument is improerly formatted.

    <Side Effects>
      Mofifies the roleinfo of the targets role in 'tuf.roledb'.
    
    <Returns>
      None.
    """

    target_files = tuf.roledb.get_roleinfo(self._rolename)['paths']

    return target_files



  def add_target(self, filepath):
    """
    <Purpose>
      Add a filepath (relative to 'self.targets_directory') to the Targets
      object.  This function does not actually create 'filepath' on the file
      system.  'filepath' must already exist on the file system.
      
      Support regular expresssions?

      >>> 
      >>>
      >>>

    <Arguments>
      filepath:

    <Exceptions>
      tuf.FormatError, if 'filepath' is improperly formatted.

    <Side Effects>
      Adds 'filepath' to this role's list of targets.  This role's
      'tuf.roledb.py' is also updated.

    <Returns>
      None.
    """
    
    # Does 'filepath' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.PATH_SCHEMA.check_match(filepath)

    filepath = os.path.abspath(filepath)
    
    if not os.path.commonprefix([self._targets_directory, filepath]) == \
                                self._targets_directory:
      message = repr(filepath)+' is not under the Repository\'s targets '+\
        'directory: '+repr(self._targets_directory)
      raise tuf.Error(message)

    # TODO: Ensure 'filepath' is an allowed target path according to the
    # parent's delegation.
    """
    for child_target in actual_child_targets:
      for allowed_child_path in allowed_child_paths:
        prefix = os.path.commonprefix([child_target, allowed_child_path])
        if prefix == allowed_child_path:
          break
    """

    # Add 'filepath' (i.e., relative to the targets directory) to the role's
    # list of targets. 
    if os.path.isfile(filepath):
      
      # Update the role's 'tuf.roledb.py' entry and 'self._target_files'.
      targets_directory_length = len(self._targets_directory) 
      roleinfo = tuf.roledb.get_roleinfo(self._rolename)
      relative_path = filepath[targets_directory_length+1:]
      if relative_path not in roleinfo['paths']:
        roleinfo['paths'].append(relative_path)
      tuf.roledb.update_roleinfo(self._rolename, roleinfo)
    
    else:
      message = repr(filepath)+' is not a valid file.'
      raise tuf.Error(message)
 

  
  def add_targets(self, list_of_targets):
    """
    <Purpose>
      Add a list of target filepaths (all relative to 'self.targets_directory').
      This function does not actually create files on the file system.  The
      list of target must already exist.
      
      >>> 
      >>>
      >>>

    <Arguments>
      list_of_targets:

    <Exceptions>

    <Side Effects>
      
    <Returns>
      None.
    """

    # Does 'list_of_targets' have the correct format?
    # Raise 'tuf.FormatError' if it is improperly formatted.
    tuf.formats.RELPATHS_SCHEMA.check_match(list_of_targets)

    # TODO: Ensure list of targets allowed paths according to the parent's
    # delegation.

    # Update the tuf.roledb entry.
    targets_directory_length = len(self._targets_directory) 
    absolute_list_of_targets = []
    relative_list_of_targets = []
    
    for target in list_of_targets:
      filepath = os.path.abspath(target)
      
      if not os.path.commonprefix([self._targets_directory, filepath]) == \
                                  self._targets_directory:
        message = repr(filepath)+' is not under the Repository\'s targets '+\
          'directory: '+repr(self._targets_directory)
        raise tuf.Error(message)
      if os.path.isfile(filepath):
        absolute_list_of_targets.append(filepath)
        relative_list_of_targets.append(filepath[targets_directory_length+1:])
      else:
        message = repr(filepath)+' is not a valid file.'
        raise tuf.Error(message)

    # Update the role's target_files and its 'tuf.roledb.py' entry.
    roleinfo = tuf.roledb.get_roleinfo(self._rolename)
    for relative_target in relative_list_of_targets:
      if relative_target not in roleinfo['paths']:
        roleinfo['paths'].append(relative_target)
    tuf.roledb.update_roleinfo(self.rolename, roleinfo)
  
  
  
  def remove_target(self, filepath):
    """
    <Purpose>
      Takes a filepath relative to the targets directory.  Regular expresssions
      would be useful here.

      >>> 
      >>>
      >>>

    <Arguments>
      filepath:
        Relative to the targets directory.

    <Exceptions>
      tuf.FormatError, if 'filepath' is improperly formatted.

      tuf.Error, if 'filepath' is not under the targets directory.

    <Side Effects>
      Modifies the target role's 'tuf.roledb.py' entry.
    
    <Returns>
      None.
    """

    # Does 'filepath' have the correct format?
    # Raise 'tuf.FormatError' if there is a mismatch.
    tuf.formats.RELPATH_SCHEMA.check_match(filepath)
   
    filepath = os.path.abspath(filepath)
    targets_directory_length = len(self._targets_directory)
    
    # Ensure 'filepath' is under the targets directory.
    if not os.path.commonprefix([self._targets_directory, filepath]) == \
                                self._targets_directory:
      message = repr(filepath)+' is not under the Repository\'s targets '+\
        'directory: '+repr(self._targets_directory)
      raise tuf.Error(message)

    relative_filepath = filepath[targets_directory_length+1:]
    
    fileinfo = tuf.roledb.get_roleinfo(self.rolename)
    if relative_filepath in fileinfo['paths']:
      fileinfo['paths'].remove(relative_filepath)

    tuf.roledb.update_roleinfo(self.rolename, fileinfo)



  def clear_targets(self):
    """
    <Purpose>
      Remove all the target filepaths in the "paths" field of self.rolename.      

      >>> 
      >>>
      >>>

    <Arguments>
      None

    <Exceptions>
      None.

    <Side Effects>
      Modifies the target role's 'tuf.roledb.py' entry.
    
    <Returns>
      None.
    """
    
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    roleinfo['paths'] = []
    
    tuf.roledb.update_roleinfo(self.rolename, roleinfo) 



  def delegate(self, rolename, public_keys, list_of_targets,
               threshold=1, restricted_paths=None, path_hash_prefixes=None):
    """
    <Purpose>
      'targets' is a list of target filepaths, and can be empty.

      >>> 
      >>>
      >>>

    <Arguments>
      rolename:

      public_keys:

      list_of_targets:

      expiration:

      restricted_paths:

    <Exceptions>
      tuf.FormatError, if any of the arguments are improperly formatted.

      tuf.Error, if the delegated role already exists.

    <Side Effects>
      A new Target object is created for 'rolename' that is accessible to the
      caller (i.e., targets.unclaimed.<rolename>).  The 'tuf.keydb.py' and
      'tuf.roledb.py' stores are updated with 'public_keys'.

    <Returns>
      None.
    """

    # Do the arguments have the correct format?
    # Raise 'tuf.FormatError' if any of the arguments are improperly formatted.
    tuf.formats.ROLENAME_SCHEMA.check_match(rolename)
    tuf.formats.ANYKEYLIST_SCHEMA.check_match(public_keys)
    tuf.formats.RELPATHS_SCHEMA.check_match(list_of_targets)
    tuf.formats.THRESHOLD_SCHEMA.check_match(threshold)
    if restricted_paths is not None:
      tuf.formats.RELPATHS_SCHEMA.check_match(restricted_paths)
    if path_hash_prefixes is not None:
      tuf.formats.PATH_HASH_PREFIXES_SCHEMA.check_match(path_hash_prefixes)
      
    full_rolename = self._rolename+'/'+rolename

    if tuf.roledb.role_exists(full_rolename):
      raise tuf.Error(repr(full_rolename)+' already delegated.')

    keyids = [] 
    keydict = {}

    # Add public keys to tuf.keydb
    for key in public_keys:
      
      try:
        tuf.keydb.add_key(key)
      except tuf.KeyAlreadyExistsError, e:
        pass
      
      keyid = key['keyid']
      key_metadata_format = tuf.keys.format_keyval_to_metadata(key['keytype'],
                                                               key['keyval'])
      new_keydict = {keyid: key_metadata_format}
      keydict.update(new_keydict)
      keyids.append(keyid)

    # Validate 'list_of_targets'.
    relative_targetpaths = []
    targets_directory_length = len(self._targets_directory)
    
    for target in list_of_targets:
      target = os.path.abspath(target)
      if not os.path.commonprefix([self._targets_directory, target]) == \
                                self._targets_directory:
        message = repr(target)+' is not under the Repository\'s targets '+\
        'directory: '+repr(self._targets_directory)
        raise tuf.Error(message)

      relative_targetpaths.append(target[targets_directory_length+1:])
    
    # Validate 'restricted_paths'.
    relative_restricted_paths = []
   
    if restricted_paths is not None: 
      for target in restricted_paths:
        target = os.path.abspath(target)
        if not os.path.commonprefix([self._targets_directory, target]) == \
                                  self._targets_directory:
          message = repr(target)+' is not under the Repository\'s targets '+\
          'directory: '+repr(self._targets_directory)
          raise tuf.Error(message)

        relative_restricted_paths.append(target[targets_directory_length+1:])
   
    # Add role to 'tuf.roledb.py'.
    expiration = tuf.formats.format_time(time.time()+TARGETS_EXPIRATION)
    roleinfo = {'name': full_rolename, 'keyids': keyids, 'signing_keyids': [],
                'threshold': threshold, 'version': 0, 'compressions': [''],
                'expires': expiration, 'signatures': [],
                'paths': relative_targetpaths, 'delegations': {'keys': {},
                'roles': []}}

    new_targets_object = Targets(self._targets_directory, full_rolename,
                                 roleinfo)
    
    # Update the 'delegations' field of the current role.
    current_roleinfo = tuf.roledb.get_roleinfo(self.rolename) 
    current_roleinfo['delegations']['keys'].update(keydict)

    # A ROLE_SCHEMA object requires only 'keyids', 'threshold', and 'paths'.
    roleinfo = {'name': full_rolename,
                'keyids': roleinfo['keyids'],
                'threshold': roleinfo['threshold'],
                'paths': roleinfo['paths']}
    if restricted_paths is not None:
      roleinfo['paths'] = relative_restricted_paths
    if path_hash_prefixes is not None:
      roleinfo['path_hash_prefixes'] = path_hash_prefixes
    
    current_roleinfo['delegations']['roles'].append(roleinfo)
    tuf.roledb.update_roleinfo(self.rolename, current_roleinfo)  
    
    # Update 'new_targets_object' attributes.
    for key in public_keys:
      new_targets_object.add_key(key)

    self.__setattr__(rolename, new_targets_object)



  def revoke(self, rolename):
    """
    <Purpose>

      >>>
      >>>
      >>>

    <Arguments>
      rolename:
        Not the full rolename ('Django' in 'targets/unclaimed/Django') of the
        role the parent role (this role) wants to revoke.

    <Exceptions>
      tuf.FormatError, if 'rolename' is improperly formatted.

    <Side Effects>

    <Returns>
      None.
    """

    tuf.formats.ROLENAME_SCHEMA.check_match(rolename) 

    # Remove from this Target's delegations dict.
    full_rolename = self.rolename+'/'+rolename
    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    
    for role in roleinfo['delegations']['roles']:
      if role['name'] == full_rolename:
        roleinfo['delegations']['roles'].remove(role)

    tuf.roledb.update_roleinfo(self.rolename, roleinfo) 
    
    # Remove from 'tuf.roledb.py'.  The delegated roles of 'rolename' are also
    # removed.
    tuf.roledb.remove_role(full_rolename)
   
    # Remove the rolename attribute from the current role.
    self.__delattr__(rolename)


  @property
  def delegations(self):
    """
    """

    roleinfo = tuf.roledb.get_roleinfo(self.rolename)
    delegations = roleinfo['delegations']

    return delegations





def _generate_and_write_metadata(rolename, filenames, write_partial,
                                 targets_directory, metadata_directory):
  """
  Helper function to generate and write the metadata of top-level roles.
  """

  root_filename = filenames[ROOT_FILENAME] 
  targets_filename = filenames[TARGETS_FILENAME] 
  release_filename = filenames[RELEASE_FILENAME] 
  timestamp_filename = filenames[TIMESTAMP_FILENAME] 
  metadata_filename = None
  metadata = None 

  roleinfo = tuf.roledb.get_roleinfo(rolename) 
  release_compressions = tuf.roledb.get_roleinfo('release')['compressions']

  if rolename == 'root':
    metadata_filename = root_filename
    metadata = generate_root_metadata(roleinfo['version'],
                                      roleinfo['expires'])
  elif rolename == 'targets':
    metadata_filename = targets_filename
    metadata = generate_targets_metadata(targets_directory,
                                         roleinfo['paths'],
                                         roleinfo['version'],
                                         roleinfo['expires'],
                                         roleinfo['delegations'])
  elif rolename == 'release':
    metadata_filename = release_filename
    metadata = generate_release_metadata(metadata_directory,
                                         roleinfo['version'],
                                         roleinfo['expires'])
  elif rolename == 'timestamp':
    metadata_filename = timestamp_filename
    metadata = generate_timestamp_metadata(release_filename,
                                           roleinfo['version'],
                                           roleinfo['expires'],
                                           release_compressions)

  signable = sign_metadata(metadata, roleinfo['signing_keyids'],
                           metadata_filename)
  
  # Increment version number if this is a new/first partial write.
  if write_partial:
    temp_signable = sign_metadata(metadata, [],
                             metadata_filename)
    temp_signable['signatures'].extend(roleinfo['signatures'])
    status = tuf.sig.get_signature_status(temp_signable, rolename)
    if len(status['good_sigs']) == 0:
      metadata['version'] = metadata['version'] + 1
      signable = sign_metadata(metadata, roleinfo['signing_keyids'],
                               metadata_filename)
  # non-partial write()
  else:
    if tuf.sig.verify(signable, rolename) and not roleinfo['partial_loaded']:
      metadata['version'] = metadata['version'] + 1
      signable = sign_metadata(metadata, roleinfo['signing_keyids'],
                               metadata_filename)
  
  # Write the metadata to file if contains a threshold of signatures. 
  signable['signatures'].extend(roleinfo['signatures']) 
  
  if tuf.sig.verify(signable, rolename) or write_partial:
    _remove_invalid_and_duplicate_signatures(signable)
    for compression in roleinfo['compressions']:
      write_metadata_file(signable, metadata_filename, compression)
    
    return signable  
  
  # 'signable' contains an invalid threshold of signatures. 
  else:
    message = 'Not enough signatures for '+repr(metadata_filename)
    raise tuf.Error(message, signable)





def _print_status(rolename, signable):
  """
  """

  status = tuf.sig.get_signature_status(signable, rolename)
  message = repr(rolename)+' role contains '+ \
    repr(len(status['good_sigs']))+' / '+ \
    repr(status['threshold'])+' signatures.'
  print(message)





def _prompt(message, result_type=str):
  """
    Prompt the user for input by printing 'message', converting
    the input to 'result_type', and returning the value to the
    caller.
  """

  return result_type(raw_input(message))





def _get_password(prompt='Password: ', confirm=False):
  """
    Return the password entered by the user.  If 'confirm'
    is True, the user is asked to enter the previously
    entered password once again.  If they match, the
    password is returned to the caller.
  """

  while True:
    # getpass() prompts the user for a password without echoing
    # the user input.
    password = getpass.getpass(prompt, sys.stderr)
    if not confirm:
      return password
    password2 = getpass.getpass('Confirm: ', sys.stderr)
    if password == password2:
      return password
    else:
      print('Mismatch; try again.')





def _check_if_partial_loaded(rolename, signable, roleinfo):
  """
  """

  status = tuf.sig.get_signature_status(signable, rolename)
  if len(status['good_sigs']) < status['threshold'] and \
                              len(status['good_sigs']) >= 1:
    roleinfo['partial_loaded'] = True





def _check_directory(directory):
  """
  <Purpose>
    Ensure 'directory' is valid and it exists.  This is not a security check,
    but a way for the caller to determine the cause of an invalid directory
    provided by the user.  If the directory argument is valid, it is returned
    normalized and as an absolute path.

  <Arguments>
    directory:
      The directory to check.

  <Exceptions>
    tuf.Error, if 'directory' could not be validated.

    tuf.FormatError, if 'directory' is not properly formatted.

  <Side Effects>
    None.

  <Returns>
    The normalized absolutized path of 'directory'.
  """

  # Does 'directory' have the correct format?
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(directory)

  # Check if the directory exists.
  if not os.path.isdir(directory):
    raise tuf.Error(repr(directory)+' directory does not exist.')

  directory = os.path.abspath(directory)
  
  return directory





def _check_role_keys(rolename):
  """
  Non-public function that verifies the public and signing keys of 'rolename'.
  If either contain an invalid threshold number of keys, raise an exception.
  'rolename' is the full rolename (e.g., 'targets/unclaimed/django'). 
  """

  # Extract the total number of public and private keys of 'rolename' from its
  # roleinfo in 'tuf.roledb'.
  roleinfo = tuf.roledb.get_roleinfo(rolename)
  total_keyids = len(roleinfo['keyids'])
  threshold = roleinfo['threshold']
  total_signatures = len(roleinfo['signatures'])
  total_signing_keys = len(roleinfo['signing_keyids'])
 
  # Raise an exception for an invalid threshold of public keys.
  if total_keyids < threshold: 
    message = repr(rolename)+' role contains '+repr(total_keyids)+' / '+ \
      repr(threshold)+' public keys.'
    raise tuf.InsufficientKeysError(message)

  # Raise an exception for an invalid threshold of signing keys.
  if total_signatures == 0 and total_signing_keys < threshold: 
    message = repr(rolename)+' role contains '+repr(total_signing_keys)+' / '+ \
      repr(threshold)+' signing keys.'
    raise tuf.InsufficientKeysError(message)





def _remove_invalid_and_duplicate_signatures(signable):
  """
    Non-public function that removes invalid signatures from 'signable'.
    'signable' may contain signatures (invalid) from previous versions
    of the metadata that were loaded with load_repository().  Invalid, or
    duplicate signatures are removed from 'signable'.
  """
  
  # Store the keyids of valid signatures.  'signature_keyids' is checked
  # for duplicates rather than comparing signature objects because PSS may
  # generate duplicate valid signatures of the same data, yet contain different
  # signatures.
  signature_keyids = []

  for signature in signable['signatures']:
    signed = signable['signed']
    keyid = signature['keyid']
    key = None

    # Remove 'signature' from 'signable' if the listed keyid does not exist
    # in 'tuf.keydb'.
    try:
      key = tuf.keydb.get_key(keyid)
    except tuf.UnknownKeyError, e:
      signable['signatures'].remove(signature)
    
    # Remove 'signature' from 'signable' if it is an invalid signature.
    if not tuf.keys.verify_signature(key, signature, signed):
      signable['signatures'].remove(signature)
    
    # Although valid, it may still need removal if it is a duplicate.  Check
    # the keyid, rather than the signature, to remove duplicate PSS signatures.
    #  PSS may generate multiple different signatures for the same keyid.
    else:
      if keyid in signature_keyids:
        signable['signatures'].remove(signature)
      
      # 'keyid' is valid and not a duplicate, so add it to 'signature_keyids'.
      else:
        signature_keyids.append(keyid)





def _delete_obsolete_metadata(metadata_directory):
  """
  Non-public function that deletes metadata files marked as removed by
  libtuf.py.  Metadata files marked as removed are not actually deleted
  until this function is called.
  """
 
  # Walk the repository's metadata 'targets' sub-directory, where all the
  # metadata for delegated roles is stored.
  targets_metadata = os.path.join(metadata_directory, 'targets')

  # The 'targets.txt' metadata is not visited, only its child delegations.
  # The 'targets/unclaimed/django.txt' role would be located in the
  # '{repository_directory}/metadata/targets/unclaimed/' directory.
  if os.path.exists(targets_metadata) and os.path.isdir(targets_metadata):
    for directory_path, junk_directories, files in os.walk(targets_metadata):
      
      # 'files' here is a list of target file names.
      for basename in files:
        metadata_path = os.path.join(directory_path, basename)
        # Strip the metadata basename and the leading path separator.
        # '{repository_directory}/metadata/targets/unclaimed/django.txt' -->
        # 'targets/unclaimed/django.txt'
        metadata_name = \
          metadata_path[len(metadata_directory):].lstrip(os.path.sep)
        
        # Strip filename extensions.  The role database does not include the
        # metadata extension.
        for metadata_extension in METADATA_EXTENSIONS: 
          if metadata_name.endswith(metadata_extension):
            metadata_name = metadata_name[:-len(metadata_extension)]
        
        # Delete the metadata file if it does not exist in 'tuf.roledb'.
        # libtuf.py might have marked 'metadata_name' as removed, but its
        # metadata file is not actually deleted yet.  Do it now.
        if not tuf.roledb.role_exists(metadata_name):
          os.remove(metadata_path) 
  




def create_new_repository(repository_directory):
  """
  <Purpose>
    Create a new repository, instantiate barebones metadata for the top-level
    roles, and return a Repository object.  On disk, create_new_repository()
    only creates the directories needed to hold the metadata and targets files.
    The repository object returned may be modified to update the newly created
    repository.  The methods of the returned object may be called to create
    actual repository files (e.g., repository.write()).

  <Arguments>
    repository_directory:
      The directory that will eventually hold the metadata and target files of
      the TUF repository.

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

  <Side Effects>
    The 'repository_directory' is created if it does not exist, including its
    metadata and targets sub-directories.

  <Returns>
    A 'tuf.libtuf.Repository' object.
  """

  # Does 'repository_directory' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(repository_directory)

  # Set the repository, metadata, and targets directories.  These directories
  # are created if they do not exist.
  repository_directory = os.path.abspath(repository_directory)
  metadata_directory = None
  targets_directory = None
  
  # Try to create 'repository_directory' if it does not exist.
  try:
    message = 'Creating '+repr(repository_directory)
    logger.info(message)
    os.makedirs(repository_directory)
  
  # 'OSError' raised if the leaf directory already exists or cannot be created.
  # Check for case where 'repository_directory' has already been created. 
  except OSError, e:
    if e.errno == errno.EEXIST:
      pass 
    else:
      raise
  
  # Set the metadata and targets directories.  The metadata directory is a
  # staged one so that the "live" repository is not affected.  The
  # staged metadata changes may be moved over to "live" after all updated
  # have been completed.
  metadata_directory = \
    os.path.join(repository_directory, METADATA_STAGED_DIRECTORY_NAME)
  targets_directory = \
    os.path.join(repository_directory, TARGETS_DIRECTORY_NAME) 
  
  # Try to create the metadata directory that will hold all of the metadata
  # files, such as 'root.txt' and 'release.txt'.
  try:
    message = 'Creating '+repr(metadata_directory)
    logger.info(message)
    os.mkdir(metadata_directory)
  
  # 'OSError' raised if the leaf directory already exists or cannot be created.
  except OSError, e:
    if e.errno == errno.EEXIST:
      pass
    else:
      raise
  
  # Try to create the targets directory that will hold all of the target files.
  try:
    message = 'Creating '+repr(targets_directory)
    logger.info(message)
    os.mkdir(targets_directory)
  except OSError, e:
    if e.errno == errno.EEXIST:
      pass
    else:
      raise
 
  # Create the bare bones repository object, where only the top-level roles
  # have been set and contain default values (e.g., Root roles has a threshold
  # of 1, expires 1 year into the future, etc.)
  repository = Repository(repository_directory, metadata_directory,
                          targets_directory)
  
  return repository



def load_repository(repository_directory):
  """
  <Purpose>
    Return a repository object containing the contents of metadata files loaded
    from the repository.

  <Arguments>
    repository_directory:

  <Exceptions>
    tuf.FormatError, if 'repository_directory' or any of the metadata files
    are improperly formatted.  Also raised if, at a minimum, the Root role
    cannot be found.

  <Side Effects>
   All the metadata files found in the repository are loaded and their contents
   stored in a libtuf.Repository object.

  <Returns>
    libtuf.Repository object.
  """
 
  # Does 'repository_directory' have the correct format?
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(repository_directory)

  # Load top-level metadata.
  repository_directory = os.path.abspath(repository_directory)
  metadata_directory = os.path.join(repository_directory,
                                    METADATA_STAGED_DIRECTORY_NAME)
  targets_directory = os.path.join(repository_directory,
                                    TARGETS_DIRECTORY_NAME)
  
  repository = None

  filenames = get_metadata_filenames(metadata_directory)
  root_filename = filenames[ROOT_FILENAME] 
  targets_filename = filenames[TARGETS_FILENAME] 
  release_filename = filenames[RELEASE_FILENAME] 
  timestamp_filename = filenames[TIMESTAMP_FILENAME]

  root_metadata = None
  targets_metadata = None
  release_metadata = None
  timestamp_metadata = None
  
  # ROOT.txt 
  if os.path.exists(root_filename):

    # Initialize the key and role metadata of the top-level roles.
    signable = tuf.util.load_json_file(root_filename)
    tuf.formats.check_signable_object_format(signable)
    root_metadata = signable['signed']  
    tuf.keydb.create_keydb_from_root_metadata(root_metadata)
    tuf.roledb.create_roledb_from_root_metadata(root_metadata)

    roleinfo = tuf.roledb.get_roleinfo('root')
    roleinfo['signatures'] = []
    for signature in signable['signatures']:
      if signature not in roleinfo['signatures']: 
        roleinfo['signatures'].append(signature)

    if os.path.exists(root_filename+'.gz'):
      roleinfo['compressions'].append('gz')
    
    _check_if_partial_loaded('root', signable, roleinfo)
    tuf.roledb.update_roleinfo('root', roleinfo)
  
  else:
    message = 'Cannot load the required root file: '+repr(root_filename)
    raise tuf.RepositoryError(message)
  
  repository = Repository(repository_directory, metadata_directory,
                          targets_directory)
   
  # TARGETS.txt
  if os.path.exists(targets_filename):
    signable = tuf.util.load_json_file(targets_filename)
    tuf.formats.check_signable_object_format(signable)
    targets_metadata = signable['signed']

    for signature in signable['signatures']:
      repository.targets.add_signature(signature)
   
    # Update 'targets.txt' in 'tuf.roledb.py' 
    roleinfo = tuf.roledb.get_roleinfo('targets')
    roleinfo['paths'] = targets_metadata['targets'].keys()
    roleinfo['version'] = targets_metadata['version']
    roleinfo['expires'] = targets_metadata['expires']
    roleinfo['delegations'] = targets_metadata['delegations']
    if os.path.exists(targets_filename+'.gz'):
      roleinfo['compressions'].append('gz')
    
    _check_if_partial_loaded('targets', signable, roleinfo)
    tuf.roledb.update_roleinfo('targets', roleinfo)

    # Add the keys specified in the delegations field of the Targets role.
    # TODO: Delegated role's are only missing the threshold value, which the
    # parent role sets.  Remember to request threshold value from parent role.
    for key_metadata in targets_metadata['delegations']['keys'].values():
      key_object = tuf.keys.format_metadata_to_key(key_metadata)
      tuf.keydb.add_key(key_object)

    for role in targets_metadata['delegations']['roles']:
      rolename = role['name'] 
      roleinfo = {'name': role['name'], 'keyids': role['keyids'],
                  'threshold': role['threshold'], 'compressions': [''],
                  'signing_keyids': [], 'signatures': [],
                  'delegations': {'keys': {},
                                  'roles': []}}
      tuf.roledb.add_role(rolename, roleinfo)
  
  else:
    pass 
 
  
  # RELEASE.txt
  if os.path.exists(release_filename):
    signable = tuf.util.load_json_file(release_filename)
    tuf.formats.check_signable_object_format(signable)
    release_metadata = signable['signed']  
    for signature in signable['signatures']:
      repository.release.add_signature(signature)

    roleinfo = tuf.roledb.get_roleinfo('release')
    roleinfo['expires'] = release_metadata['expires']
    roleinfo['version'] = release_metadata['version']
    if os.path.exists(release_filename+'.gz'):
      roleinfo['compressions'].append('gz')
    
    _check_if_partial_loaded('release', signable, roleinfo)
    tuf.roledb.update_roleinfo('release', roleinfo)
  
  else:
    pass 
 

  # TIMESTAMP.txt 
  if os.path.exists(timestamp_filename):
    signable = tuf.util.load_json_file(timestamp_filename)
    timestamp_metadata = signable['signed']  
    for signature in signable['signatures']:
      repository.timestamp.add_signature(signature)

    roleinfo = tuf.roledb.get_roleinfo('timestamp')
    roleinfo['expires'] = timestamp_metadata['expires']
    roleinfo['version'] = timestamp_metadata['version']
    if os.path.exists(timestamp_filename+'.gz'):
      roleinfo['compressions'].append('gz')
    
    _check_if_partial_loaded('timestamp', signable, roleinfo)
    tuf.roledb.update_roleinfo('timestamp', roleinfo)
  
  else:
    pass
 
  # Load delegated targets metadata.
  # Walk the 'targets/' directory and generate the fileinfo for all
  # the files listed there.  This information is stored in the 'meta'
  # field of the release metadata object.
  targets_objects = {}
  targets_objects['targets'] = repository.targets
  targets_metadata_directory = os.path.join(metadata_directory,
                                            TARGETS_DIRECTORY_NAME)
  if os.path.exists(targets_metadata_directory) and \
                    os.path.isdir(targets_metadata_directory):
    for root, directories, files in os.walk(targets_metadata_directory):
      
      # 'files' here is a list of target file names.
      for basename in files:
        metadata_path = os.path.join(root, basename)
        metadata_name = \
          metadata_path[len(metadata_directory):].lstrip(os.path.sep)
        if metadata_name.endswith(METADATA_EXTENSION): 
          extension_length = len(METADATA_EXTENSION)
          metadata_name = metadata_name[:-extension_length]
        else:
          continue
       
        signable = None
        try:
          signable = tuf.util.load_json_file(metadata_path)
        except (ValueError, IOError), e:
          continue
        
        metadata_object = signable['signed']
      
        roleinfo = tuf.roledb.get_roleinfo(metadata_name)
        roleinfo['signatures'].extend(signable['signatures'])
        roleinfo['version'] = metadata_object['version']
        roleinfo['expires'] = metadata_object['expires']
        roleinfo['paths'] = metadata_object['targets'].keys()
        roleinfo['delegations'] = metadata_object['delegations']

        if os.path.exists(metadata_path+'.gz'):
          roleinfo['compressions'].append('gz')
        
        _check_if_partial_loaded(metadata_name, signable, roleinfo)
        tuf.roledb.update_roleinfo(metadata_name, roleinfo)

        new_targets_object = Targets(targets_directory, metadata_name, roleinfo)
        targets_object = \
          targets_objects[tuf.roledb.get_parent_rolename(metadata_name)]
        targets_objects[metadata_name] = new_targets_object
        targets_object.__setattr__(os.path.basename(metadata_name),
                                   new_targets_object)

        # Add the keys specified in the delegations field of the Targets role.
        for key_metadata in metadata_object['delegations']['keys'].values():
          key_object = tuf.keys.format_metadata_to_key(key_metadata)
          try: 
            tuf.keydb.add_key(key_object)
          except tuf.KeyAlreadyExistsError, e:
            pass
        
        for role in metadata_object['delegations']['roles']:
          rolename = role['name'] 
          roleinfo = {'name': role['name'], 'keyids': role['keyids'],
                      'threshold': role['threshold'],
                      'compressions': [''], 'signing_keyids': [],
                      'signatures': [],
                      'partial_loaded': False,
                      'delegations': {'keys': {},
                                      'roles': []}}
          tuf.roledb.add_role(rolename, roleinfo)

  return repository





def generate_and_write_rsa_keypair(filepath, bits=DEFAULT_RSA_KEY_BITS,
                                   password=None):
  """
  <Purpose>
    Generate an RSA key file, create an encrypted PEM string (using 'password'
    as the pass phrase), and store it in 'filepath'.  The public key portion of
    the generated RSA key is stored in <'filepath'>.pub.  Which cryptography
    library performs the cryptographic decryption is determined by the string
    set in 'tuf.conf.RSA_CRYPTO_LIBRARY'.  PyCrypto currently supported.  The
    PEM private key is encrypted with 3DES and CBC the mode of operation.  The
    password is strengthened with PBKDF1-MD5.

  <Arguments>
    filepath:
      The public and private key files are saved to <filepath>.pub, <filepath>,
      respectively.
    
    bits:
      The number of bits of the generated RSA key. 

    password:
      The password used to encrypt 'filepath'.

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

  <Side Effects>
    Writes key files to '<filepath>' and '<filepath>.pub'.

  <Returns>
    None.
  """

  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of
  # objects and object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # Does 'bits' have the correct format?
  tuf.formats.RSAKEYBITS_SCHEMA.check_match(bits)

  # If the caller does not provide a password argument, prompt for one.
  if password is None:
    message = 'Enter a password for the RSA key file: '
    password = _get_password(message, confirm=True)

  # Does 'password' have the correct format?
  tuf.formats.PASSWORD_SCHEMA.check_match(password)
 
  #  Generate public and private RSA keys, encrypted the private portion
  # and store them in PEM format.
  rsa_key = tuf.keys.generate_rsa_key(bits)
  public = rsa_key['keyval']['public']
  private = rsa_key['keyval']['private']
  encrypted_pem = tuf.keys.create_rsa_encrypted_pem(private, password) 
 
  # Write public key (i.e., 'public', which is in PEM format) to
  # '<filepath>.pub'.  If the parent directory of filepath does not exist,
  # create it (and all its parent directories, if necessary).
  tuf.util.ensure_parent_dir(filepath)

  with open(filepath+'.pub', 'w') as file_object:
    file_object.write(public)

  # Write the private key in encrypted PEM format to '<filepath>'.
  # Unlike the public key file, the private key does not have a file
  # extension.
  with open(filepath, 'w') as file_object:
    file_object.write(encrypted_pem)





def import_rsa_privatekey_from_file(filepath, password=None):
  """
  <Purpose>
    Import the encrypted PEM file in 'filepath', decrypt it, and return the key
    object in 'tuf.formats.RSAKEY_SCHEMA' format.

    Which cryptography library performs the cryptographic decryption is
    determined by the string set in 'tuf.conf.RSA_CRYPTO_LIBRARY'.  PyCrypto
    currently supported.

    The PEM private key is encrypted with 3DES and CBC the mode of operation.
    The password is strengthened with PBKDF1-MD5.

  <Arguments>
    filepath:
      <filepath> file, an RSA encrypted PEM file.  Unlike the public RSA PEM
      key file, 'filepath' does not have an extension.
    
    password:
      The passphrase to decrypt 'filepath'.

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

  <Side Effects>
    The contents of 'filepath' is read, decrypted, and the key stored.

  <Returns>
    An RSA key object, conformant to 'tuf.formats.RSAKEY_SCHEMA'.
  """

  # Does 'filepath' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # If the caller does not provide a password argument, prompt for one.
  if password is None:
    message = 'Enter a password for the encrypted RSA key file: '
    password = _get_password(message, confirm=True)

  # Does 'password' have the correct format?
  tuf.formats.PASSWORD_SCHEMA.check_match(password)

  encrypted_pem = None

  # Read the contents of 'filepath' that should be an encrypted PEM.
  with open(filepath, 'rb') as file_object:
    encrypted_pem = file_object.read()

  # Convert 'encrypted_pem' to 'tuf.formats.RSAKEY_SCHEMA' format.
  rsa_key = tuf.keys.import_rsakey_from_encrypted_pem(encrypted_pem, password)
  
  return rsa_key





def import_rsa_publickey_from_file(filepath):
  """
  <Purpose>
    Import the RSA key stored in 'filepath'.  The key object returned is a TUF
    key, specifically 'tuf.formats.RSAKEY_SCHEMA'.  If the RSA PEM in 'filepath'
    contains a private key, it is discarded.

    Which cryptography library performs the cryptographic decryption is
    determined by the string set in 'tuf.conf.RSA_CRYPTO_LIBRARY'.  PyCrypto
    currently supported.  If the RSA PEM in 'filepath' contains a private key,
    it is discarded.

  <Arguments>
    filepath:
      <filepath>.pub file, an RSA PEM file.
    
  <Exceptions>
    tuf.FormatError, if 'filepath' is improperly formatted.

  <Side Effects>
    'filepath' is read and its contents extracted.

  <Returns>
    An RSA key object conformant to 'tuf.formats.RSAKEY_SCHEMA'.
  """

  # Does 'filepath' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # Read the contents of the key file that should be in PEM format and contains
  # the public portion of the RSA key.
  with open(filepath, 'rb') as file_object:
    rsa_pubkey_pem = file_object.read()

  # Convert 'rsa_pubkey_pem' in 'tuf.formats.RSAKEY_SCHEMA' format.
  rsakey_dict = tuf.keys.format_rsakey_from_pem(rsa_pubkey_pem)

  return rsakey_dict





def generate_and_write_ed25519_keypair(filepath, password=None):
  """
  <Purpose>
    Generate an ED25519 key file, create an encrypted TUF key (using 'password'
    as the pass phrase), and store it in 'filepath'.  The public key portion of
    the generated ED25519 key is stored in <'filepath'>.pub.  Which cryptography
    library performs the cryptographic decryption is determined by the string
    set in 'tuf.conf.ED25519_CRYPTO_LIBRARY'.
    
    PyCrypto currently supported.  The ED25519 private key is encrypted with
    AES-256 and CTR the mode of operation.  The password is strengthened with
    PBKDF2-HMAC-SHA256.

  <Arguments>
    filepath:
      The public and private key files are saved to <filepath>.pub and
      <filepath>, respectively.
    
    password:
      The password, or passphrase, to encrypt the private portion of the
      generated ed25519 key.  A symmetric encryption key is derived from
      'password', so it is not directly used.

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.
    
    tuf.CryptoError, if 'filepath' cannot be encrypted.

    tuf.UnsupportedLibraryError, if 'filepath' cannot be encrypted due to an
    invalid configuration setting (i.e., invalid 'tuf.conf.py' setting).

  <Side Effects>
    Writes key files to '<filepath>' and '<filepath>.pub'.

  <Returns>
    None.
  """
  
  # Does 'filepath' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # If the caller does not provide a password argument, prompt for one.
  if password is None:
    message = 'Enter a password for the ED25519 key: '
    password = _get_password(message, confirm=True)

  # Does 'password' have the correct format?
  tuf.formats.PASSWORD_SCHEMA.check_match(password)

  # Generate a new ED25519 key object and encrypt it.  The cryptography library
  # used is determined by the user, or by default (set in
  # 'tuf.conf.ED25519_CRYPTO_LIBRARY').  Raise 'tuf.CryptoError' or
  # 'tuf.UnsupportedLibraryError', if 'ed25519_key' cannot be encrypted.
  ed25519_key = tuf.keys.generate_ed25519_key()
  encrypted_key = tuf.keys.encrypt_key(ed25519_key, password) 

  # ed25519 public key file contents in metadata format (i.e., does not include
  # the keyid portion).
  keytype = ed25519_key['keytype']
  keyval = ed25519_key['keyval']
  ed25519key_metadata_format = \
    tuf.keys.format_keyval_to_metadata(keytype, keyval, private=False)
  
  # Write the public key, conformant to 'tuf.formats.KEY_SCHEMA', to
  # '<filepath>.pub'.
  tuf.util.ensure_parent_dir(filepath)

  with open(filepath+'.pub', 'w') as file_object:
    file_object.write(json.dumps(ed25519key_metadata_format))

  # Write the encrypted key string, conformant to
  # 'tuf.formats.ENCRYPTEDKEY_SCHEMA', to '<filepath>'.
  with open(filepath, 'w') as file_object:
    file_object.write(encrypted_key)





def import_ed25519_publickey_from_file(filepath):
  """
  <Purpose>
    Load the ED25519 public key object (conformant to 'tuf.formats.KEY_SCHEMA')
    stored in 'filepath'.  Return 'filepath' in tuf.formats.ED25519KEY_SCHEMA
    format.
    
    If the TUF key object in 'filepath' contains a private key, it is discarded.

  <Arguments>
    filepath:
      <filepath>.pub file, a TUF public key file.
    
  <Exceptions>
    tuf.FormatError, if 'filepath' is improperly formatted or is an unexpected
    key type.

  <Side Effects>
    The contents of 'filepath' is read and saved.

  <Returns>
    An ED25519 key object conformant to 'tuf.formats.ED25519KEY_SCHEMA'.
  """

  # Does 'filepath' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # ED25519 key objects are saved in json and metadata format.  Return the
  # loaded key object in tuf.formats.ED25519KEY_SCHEMA' format that also
  # includes the keyid.
  ed25519_key_metadata = tuf.util.load_json_file(filepath)
  ed25519_key = tuf.keys.format_metadata_to_key(ed25519_key_metadata)
  
  # Raise an exception if an unexpected key type is imported. 
  if ed25519_key['keytype'] != 'ed25519':
    message = 'Invalid key type loaded: '+repr(ed25519_key['keytype'])
    raise tuf.FormatError(message)

  return ed25519_key





def import_ed25519_privatekey_from_file(filepath, password=None):
  """
  <Purpose>
    Import the encrypted ed25519 TUF key file in 'filepath', decrypt it, and
    return the key object in 'tuf.formats.ED25519KEY_SCHEMA' format.

    Which cryptography library performs the cryptographic decryption is
    determined by the string set in 'tuf.conf.ED25519_CRYPTO_LIBRARY'.  PyCrypto
    currently supported.

    The TUF private key (may also contain the public part) is encrypted with AES
    256 and CTR the mode of operation.  The password is strengthened with
    PBKDF2-HMAC-SHA256.

  <Arguments>
    filepath:
      <filepath> file, an RSA encrypted TUF key file.
    
    password:
      The password, or passphrase, to import the private key (i.e., the
      encrypted key file 'filepath' must be decrypted before the ed25519 key
      object can be returned.

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted or the imported
    key object contains an invalid key type (i.e., not 'ed25519').

    tuf.CryptoError, if 'filepath' cannot be decrypted.

    tuf.UnsupportedLibraryError, if 'filepath' cannot be decrypted due to an
    invalid configuration setting (i.e., invalid 'tuf.conf.py' setting).

  <Side Effects>
    'password' is used to decrypt the 'filepath' key file.

  <Returns>
    An ed25519 key object of the form: 'tuf.formats.ED25519KEY_SCHEMA'.
  """

  # Does 'filepath' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filepath)

  # If the caller does not provide a password argument, prompt for one.
  if password is None:
    message = 'Enter a password for the encrypted ED25519 key file: '
    password = _get_password(message, confirm=True)

  # Does 'password' have the correct format?
  tuf.formats.PASSWORD_SCHEMA.check_match(password)

  # Store the encrypted contents of 'filepath' prior to calling the decryption
  # routine.
  encrypted_key = None

  with open(filepath, 'rb') as file_object:
    encrypted_key = file_object.read()

  # Decrypt the loaded key file, calling the appropriate cryptography library
  # (i.e., set by the user) and generating the derived encryption key from
  # 'password'.  Raise 'tuf.CryptoError' or 'tuf.UnsupportedLibraryError' if the
  # decryption fails.
  key_object = tuf.keys.decrypt_key(encrypted_key, password)

  # Raise an exception if an unexpected key type is imported. 
  if key_object['keytype'] != 'ed25519':
    message = 'Invalid key type loaded: '+repr(key_object['keytype'])
    raise tuf.FormatError(message)

  return key_object





def get_metadata_filenames(metadata_directory=None):
  """
  <Purpose>
    Return a dictionary containing the filenames of the top-level roles.
    If 'metadata_directory' is set to 'metadata', the dictionary
    returned would contain:

    filenames = {'root': 'metadata/root.txt',
                 'targets': 'metadata/targets.txt',
                 'release': 'metadata/release.txt',
                 'timestamp': 'metadata/timestamp.txt'}

    If the metadata directory is not set by the caller, the current
    directory is used.

  <Arguments>
    metadata_directory:
      The directory containing the metadata files.

  <Exceptions>
    tuf.FormatError, if 'metadata_directory' is improperly formatted.

  <Side Effects>
    None.

  <Returns>
    A dictionary containing the expected filenames of the top-level
    metadata files, such as 'root.txt' and 'release.txt'.
  """
  
  # Does 'metadata_directory' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(metadata_directory)

  if metadata_directory is None:
    metadata_directory = '.'

  # Does 'metadata_directory' have the correct format?
  # Raise 'tuf.FormatError' if there is a mismatch. 
  tuf.formats.PATH_SCHEMA.check_match(metadata_directory)

  # Store the filepaths of the top-level roles, including the
  # 'metadata_directory' for each one.
  filenames = {}

  filenames[ROOT_FILENAME] = \
    os.path.join(metadata_directory, ROOT_FILENAME)
  
  filenames[TARGETS_FILENAME] = \
    os.path.join(metadata_directory, TARGETS_FILENAME)
  
  filenames[RELEASE_FILENAME] = \
    os.path.join(metadata_directory, RELEASE_FILENAME)
  
  filenames[TIMESTAMP_FILENAME] = \
    os.path.join(metadata_directory, TIMESTAMP_FILENAME)

  return filenames





def get_metadata_file_info(filename):
  """
  <Purpose>
    Retrieve the file information of 'filename'.  The object returned
    conforms to 'tuf.formats.FILEINFO_SCHEMA'.  The information
    generated for 'filename' is stored in metadata files like 'targets.txt'.
    The fileinfo object returned has the form:
    fileinfo = {'length': 1024,
                'hashes': {'sha256': 1233dfba312, ...},
                'custom': {...}}

  <Arguments>
    filename:
      The metadata file whose file information is needed.  It must exist.

  <Exceptions>
    tuf.FormatError, if 'filename' is improperly formatted.

    tuf.Error, if 'filename' doesn't exist.

  <Side Effects>
    The file is opened and information about the file is generated,
    such as file size and its hash.

  <Returns>
    A dictionary conformant to 'tuf.formats.FILEINFO_SCHEMA'.  This
    dictionary contains the length, hashes, and custom data about the
    'filename' metadata file.
  """

  # Does 'filename' have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(filename)

  if not os.path.isfile(filename):
    message = repr(filename)+' is not a file.'
    raise tuf.Error(message)
  
  # Note: 'filehashes' is a dictionary of the form
  # {'sha256': 1233dfba312, ...}.  'custom' is an optional
  # dictionary that a client might define to include additional
  # file information, such as the file's author, version/revision
  # numbers, etc.
  filesize, filehashes = tuf.util.get_file_details(filename)
  custom = None

  return tuf.formats.make_fileinfo(filesize, filehashes, custom)





def generate_root_metadata(version, expiration_date):
  """
  <Purpose>
    Create the root metadata.  'tuf.roledb.py' and 'tuf.keydb.py' are read and
    the information returned by these modules is used to generate the root
    metadata object.

  <Arguments>
    version:
      The metadata version number.  Clients use the version number to
      determine if the downloaded version is newer than the one currently
      trusted.
    
    expiration_date:
      The expiration date, in UTC, of the metadata file.  Conformant to
      'tuf.formats.TIME_SCHEMA'.

  <Exceptions>
    tuf.FormatError, if the generated root metadata object could not
    be generated with the correct format.

    tuf.Error, if an error is encountered while generating the root
    metadata object.
  
  <Side Effects>
    The contents of 'tuf.keydb.py' and 'tuf.roledb.py' are read.

  <Returns>
    A root metadata object, conformant to 'tuf.formats.ROOT_SCHEMA'.
  """

  # Do the arguments have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if any of the arguments are improperly formatted.
  tuf.formats.METADATAVERSION_SCHEMA.check_match(version)
  tuf.formats.TIME_SCHEMA.check_match(expiration_date)

  # The role and key dictionaries to be saved in the root metadata object.
  # Conformant to 'ROLEDICT_SCHEMA' and 'KEYDICT_SCHEMA', respectively. 
  roledict = {}
  keydict = {}

  # Extract the role, threshold, and keyid information of the top-level roles,
  # which Root stores in its metadata.  The necessary role metadata is generated
  # from this information.
  for rolename in ['root', 'targets', 'release', 'timestamp']:
    
    # If a top-level role is missing from 'tuf.roledb.py', raise an exception.
    if not tuf.roledb.role_exists(rolename):
      raise tuf.Error(repr(rolename)+' not in "tuf.roledb".')
   
    # Keep track of the keys loaded so that duplicates is avoided.
    keyids = []

    # Generate keys for the keyids listed by the role being processed.
    for keyid in tuf.roledb.get_role_keyids(rolename):
      key = tuf.keydb.get_key(keyid)

      # If 'key' is an RSA key, it would conform to 'tuf.formats.RSAKEY_SCHEMA',
      # and have the form:
      # {'keytype': 'rsa',
      #  'keyid': keyid,
      #  'keyval': {'public': '-----BEGIN RSA PUBLIC KEY----- ...',
      #             'private': '-----BEGIN RSA PRIVATE KEY----- ...'}}
      keyid = key['keyid']
      if keyid not in keydict:
        
        # This appears to be a new keyid.  Let's generate the key for it.
        if key['keytype'] in ['rsa', 'ed25519']:
          keytype = key['keytype']
          keyval = key['keyval']
          keydict[keyid] = \
            tuf.keys.format_keyval_to_metadata(keytype, keyval)
        
        # This is not a recognized key.  Raise an exception.
        else:
          raise tuf.Error('Unsupported keytype: '+keyid)
      
      # Do we have a duplicate?
      if keyid in keyids:
        raise tuf.Error('Same keyid listed twice: '+keyid)
      
      # Add the loaded keyid for the role being processed.
      keyids.append(keyid)
    
    # Generate and store the role data belonging to the processed role.
    role_threshold = tuf.roledb.get_role_threshold(rolename)
    role_metadata = tuf.formats.make_role_metadata(keyids, role_threshold)
    roledict[rolename] = role_metadata

  # Generate the root metadata object.
  root_metadata = tuf.formats.RootFile.make_metadata(version, expiration_date,
                                                     keydict, roledict)

  return root_metadata 





def generate_targets_metadata(targets_directory, target_files, version,
                              expiration_date, delegations=None):
  """
  <Purpose>
    Generate the targets metadata object. The targets in 'target_files' must
    exist at the same path they should on the repo.  'target_files' is a list of
    targets.  The 'custom' field of the targets metadata is not currently
    supported.

  <Arguments>
    targets_directory:
      The directory containing the target files and directories of the 
      repository.

    target_files:
      The target files tracked by 'targets.txt'.  'target_files' is a list of
      target paths that are relative to the targets directory (e.g.,
      ['file1.txt', 'Django/module.py']).

    version:
      The metadata version number.  Clients use the version number to
      determine if the downloaded version is newer than the one currently
      trusted.

    expiration_date:
      The expiration date, in UTC, of the metadata file.  Conformant to
      'tuf.formats.TIME_SCHEMA'.

    delegations:
      The delegations made by the targets role to be generated.  'delegations'
      must match 'tuf.formats.DELEGATIONS_SCHEMA'.
  
  <Exceptions>
    tuf.FormatError, if an error occurred trying to generate the targets
    metadata object.

    tuf.Error, if any of the target files cannot be read. 

  <Side Effects>
    The target files are read and file information generated about them.

  <Returns>
    A targets metadata object, conformant to 'tuf.formats.TARGETS_SCHEMA'.
  """

  # Do the arguments have the correct format?
  # Ensure the arguments have the appropriate number of objects and object
  # types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if there is a mismatch.
  tuf.formats.PATH_SCHEMA.check_match(targets_directory)
  tuf.formats.PATHS_SCHEMA.check_match(target_files)
  tuf.formats.METADATAVERSION_SCHEMA.check_match(version)
  tuf.formats.TIME_SCHEMA.check_match(expiration_date)

  if delegations is not None:
    tuf.formats.DELEGATIONS_SCHEMA.check_match(delegations)
  
  # Store the file attributes of targets in 'target_files'.  'filedict',
  # conformant to 'tuf.formats.FILEDICT_SCHEMA', is added to the targets
  # metadata object returned.
  filedict = {}

  # Ensure the user is aware of a non-existent 'target_directory', and convert
  # it to its abosolute path, if it exists.
  targets_directory = _check_directory(targets_directory)

  # Generate the fileinfo of all the target files listed in 'target_files'.
  for target in target_files:
   
    # The root-most folder of the targets directory should not be included.
    # (e.g., 'targets/more_targets/somefile.txt' -> 'more_targets/somefile.txt')
    relative_targetpath = target
    target_path = os.path.join(targets_directory, target)
   
    # Ensure all target files listed in 'target_files' exist.  If just one of
    # these files does not exist, raise an exception.
    if not os.path.exists(target_path):
      message = repr(target_path)+' cannot be read.  Unable to generate '+ \
        'targets metadata.'
      raise tuf.Error(message)
    
    filedict[relative_targetpath] = get_metadata_file_info(target_path)

  # Generate the targets metadata object.
  targets_metadata = tuf.formats.TargetsFile.make_metadata(version,
                                                           expiration_date,
                                                           filedict,
                                                           delegations)

  return targets_metadata





def generate_release_metadata(metadata_directory, version, expiration_date):
  """
  <Purpose>
    Create the release metadata.  The minimum metadata must exist
    (i.e., 'root.txt' and 'targets.txt'). This will also look through
    the 'targets/' directory in 'metadata_directory' and the resulting
    release file will list all the delegated roles.

  <Arguments>
    metadata_directory:
      The directory containing the 'root.txt' and 'targets.txt' metadata
      files.
    
    version:
      The metadata version number.  Clients use the version number to
      determine if the downloaded version is newer than the one currently
      trusted.

    expiration_date:
      The expiration date, in UTC, of the metadata file.
      Conformant to 'tuf.formats.TIME_SCHEMA'.

  <Exceptions>
    tuf.FormatError, if 'metadata_directory' is improperly formatted.

    tuf.Error, if an error occurred trying to generate the release metadata
    object.

  <Side Effects>
    The 'root.txt' and 'targets.txt' files are read.

  <Returns>
    The release metadata object, conformant to 'tuf.formats.RELEASE_SCHEMA'.
  """

  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.PATH_SCHEMA.check_match(metadata_directory)
  tuf.formats.METADATAVERSION_SCHEMA.check_match(version)
  tuf.formats.TIME_SCHEMA.check_match(expiration_date)

  metadata_directory = _check_directory(metadata_directory)

  # Retrieve the full filepath of the root and targets metadata file.
  root_filename = os.path.join(metadata_directory, ROOT_FILENAME)
  targets_filename = os.path.join(metadata_directory, TARGETS_FILENAME)

  # Retrieve the fileinfo of 'root.txt' and 'targets.txt'.  This file
  # information includes data such as file length, hashes of the file, etc.
  filedict = {}
  filedict[ROOT_FILENAME] = get_metadata_file_info(root_filename)
  filedict[TARGETS_FILENAME] = get_metadata_file_info(targets_filename)

  # Add compressed versions of the 'targets.txt' and 'root.txt' metadata,
  # if they exist.
  for extension in SUPPORTED_COMPRESSION_EXTENSIONS:
    compressed_root_filename = root_filename+extension
    compressed_targets_filename = targets_filename+extension
    
    # If the compressed versions of the root and targets metadata is found,
    # add their file attributes to 'filedict'.
    if os.path.exists(compressed_root_filename):
      filedict[ROOT_FILENAME+extension] = \
        get_metadata_file_info(compressed_root_filename)
    if os.path.exists(compressed_targets_filename): 
      filedict[TARGETS_FILENAME+extension] = \
        get_metadata_file_info(compressed_targets_filename)

  # Walk the 'targets/' directory and generate the fileinfo of all the role
  # files found.  This information is stored in the 'meta' field of the release
  # metadata object.
  targets_metadata = os.path.join(metadata_directory, 'targets')
  if os.path.exists(targets_metadata) and os.path.isdir(targets_metadata):
    for directory_path, junk_directories, files in os.walk(targets_metadata):
      
      # 'files' here is a list of file names.
      for basename in files:
        metadata_path = os.path.join(directory_path, basename)
        metadata_name = \
          metadata_path[len(metadata_directory):].lstrip(os.path.sep)
        
        # All delegated roles are added to the release file, including
        # compressed versions.
        for metadata_extension in METADATA_EXTENSIONS: 
          if metadata_name.endswith(metadata_extension):
            rolename = metadata_name[:-len(metadata_extension)]
            
            # Obsolete role files may still be found.  Ensure only roles loaded
            # in the roledb are included in the release metadata.
            if tuf.roledb.role_exists(rolename):
              filedict[metadata_name] = get_metadata_file_info(metadata_path)

  # Generate the release metadata object.
  release_metadata = tuf.formats.ReleaseFile.make_metadata(version,
                                                           expiration_date,
                                                           filedict)

  return release_metadata





def generate_timestamp_metadata(release_filename, version,
                                expiration_date, compressions=()):
  """
  <Purpose>
    Generate the timestamp metadata object.  The 'release.txt' file must exist.

  <Arguments>
    release_filename:
      The required filename of the release metadata file.
    
    version:
      The timestamp's version number.  Clients use the version number to
      determine if the downloaded version is newer than the one currently
      trusted.

    expiration_date:
      The expiration date, in UTC, of the metadata file, conformant to
      'tuf.formats.TIME_SCHEMA'.

    compressions:
      Compression extensions (e.g., 'gz').  If 'release.txt' is also saved in
      compressed form, these compression extensions should be stored in
      'compressions' so the compressed timestamp files can be added to the
      timestamp metadata object.

  <Exceptions>
    tuf.FormatError, if the generated timestamp metadata object cannot be
    formatted correctly, or one of the arguments is improperly formatted.

  <Side Effects>
    None.

  <Returns>
    A timestamp metadata object, conformant to 'tuf.formats.TIMESTAMP_SCHEMA'.
  """
  
  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.PATH_SCHEMA.check_match(release_filename)
  tuf.formats.METADATAVERSION_SCHEMA.check_match(version)
  tuf.formats.TIME_SCHEMA.check_match(expiration_date)
  tuf.formats.COMPRESSIONS_SCHEMA.check_match(compressions)

  # Retrieve the fileinfo of the release metadata file.
  # This file information contains hashes, file length, custom data, etc.
  fileinfo = {}
  fileinfo[RELEASE_FILENAME] = get_metadata_file_info(release_filename)

  # Save the fileinfo of the compressed versions of 'timestamp.txt'
  # in 'fileinfo'.  Log the files included in 'fileinfo'.
  for file_extension in compressions:
    
    compressed_filename = release_filename + '.' + file_extension
    try:
      compressed_fileinfo = get_metadata_file_info(compressed_filename)
    
    except:
      logger.warn('Cannot get fileinfo about '+str(compressed_filename))
    
    else:
      logger.info('Including fileinfo about '+str(compressed_filename))
      fileinfo[RELEASE_FILENAME+'.' + file_extension] = compressed_fileinfo

  # Generate the timestamp metadata object.
  timestamp_metadata = tuf.formats.TimestampFile.make_metadata(version,
                                                               expiration_date,
                                                               fileinfo)

  return timestamp_metadata





def sign_metadata(metadata_object, keyids, filename):
  """
  <Purpose>
    Sign a metadata object. If any of the keyids have already signed the file,
    the old signature is replaced.  The keys in 'keyids' must already be
    loaded in 'tuf.keydb'.

  <Arguments>
    metadata_object:
      The metadata object to sign.  For example, 'metadata' might correspond to
      'tuf.formats.ROOT_SCHEMA' or 'tuf.formats.TARGETS_SCHEMA'.

    keyids:
      The keyids list of the signing keys.

    filename:
      The intended filename of the signed metadata object.
      For example, 'root.txt' or 'targets.txt'.  This function
      does NOT save the signed metadata to this filename.

  <Exceptions>
    tuf.FormatError, if a valid 'signable' object could not be generated or
    the arguments are improperly formatted.

    tuf.Error, if an invalid keytype was found in the keystore. 
  
  <Side Effects>
    None.

  <Returns>
    A signable object conformant to 'tuf.formats.SIGNABLE_SCHEMA'.
  """

  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.ANYROLE_SCHEMA.check_match(metadata_object)  
  tuf.formats.KEYIDS_SCHEMA.check_match(keyids)
  tuf.formats.PATH_SCHEMA.check_match(filename)

  # Make sure the metadata is in 'signable' format.  That is,
  # it contains a 'signatures' field containing the result
  # of signing the 'signed' field of 'metadata' with each
  # keyid of 'keyids'.
  signable = tuf.formats.make_signable(metadata_object)

  # Sign the metadata with each keyid in 'keyids'.
  for keyid in keyids:
    
    # Load the signing key.
    key = tuf.keydb.get_key(keyid)
    logger.info('Signing '+repr(filename)+' with '+key['keyid'])

    # Create a new signature list.  If 'keyid' is encountered,
    # do not add it to new list.
    signatures = []
    for signature in signable['signatures']:
      if not keyid == signature['keyid']:
        signatures.append(signature)
    signable['signatures'] = signatures

    # Generate the signature using the appropriate signing method.
    if key['keytype'] in SUPPORTED_KEY_TYPES:
      if len(key['keyval']['private']):
        signed = signable['signed']
        signature = tuf.keys.create_signature(key, signed)
        signable['signatures'].append(signature)
      else:
        logger.warn('Private key unset.  Skipping: '+repr(keyid))
    
    else:
      raise tuf.Error('The keydb contains a key with an invalid key type.')

  # Raise 'tuf.FormatError' if the resulting 'signable' is not formatted
  # correctly.
  tuf.formats.check_signable_object_format(signable)

  return signable





def write_metadata_file(metadata, filename, compression=''):
  """
  <Purpose>
    Write the 'metadata' signable object to 'filename', and the compressed
    version of the metadata file if 'compression' is set.

  <Arguments>
    metadata:
      The object that will be saved to 'filename', conformant to
      'tuf.formats.SIGNABLE_SCHEMA'.

    filename:
      The filename of the metadata to be written (e.g., 'root.txt').
      If 'compression' is set, the compressions extention is appended to
      'filename'.

    compression:
      Specify the algorithm, as a string, to compress the file; otherwise, the
      file will be left uncompressed. Available options are 'gz' (gzip).

  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

    tuf.Error, if the directory of 'filename' does not exist.

    Any other runtime (e.g., IO) exception.

  <Side Effects>
    The 'filename' (or the compressed filename) file is created or overwritten
    if it exists.

  <Returns>
    The file path of the written metadata.
  """

  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.SIGNABLE_SCHEMA.check_match(metadata)
  tuf.formats.PATH_SCHEMA.check_match(filename)
  tuf.formats.COMPRESSION_SCHEMA.check_match(compression)

  # Verify the directory of 'filename' and convert 'filename' to its absolute
  # path.
  _check_directory(os.path.dirname(filename))
  filename = os.path.abspath(filename)

  file_object = None
  
  # We may modify the filename, depending on the compression algorithm, so we
  # store it separately.
  filename_with_compression = filename

  # Take care of compression by opening the appropriate file object and updating
  # 'filename_with_compression', if necessary.
  if not len(compression):
    logger.info('No compression for '+str(filename))
    file_object = open(filename_with_compression, 'w')
  
  elif compression == 'gz':
    logger.info('gzip compression for '+str(filename))
    filename_with_compression += '.gz'
    file_object = gzip.open(filename_with_compression, 'w')
  
  else:
    raise tuf.FormatError('Unknown compression algorithm: '+str(compression))

  try:
    tuf.formats.PATH_SCHEMA.check_match(filename_with_compression)
    logger.info('Writing to '+str(filename_with_compression))

    # The metadata object is saved to 'filename_with_compression'.  The keys
    # of the objects are sorted and indentation is used.
    json.dump(metadata, file_object, indent=1, sort_keys=True)

    file_object.write('\n')
  except:
    # Raise any runtime exception.
    raise
  
  else:
    # Otherwise, return the written filename if there are no exceptions.
    return filename_with_compression
  
  finally:
    # Always close the file.
    file_object.close()





def write_delegated_metadata_file(repository_directory, targets_directory,
                                  rolename, roleinfo, write_partial=False):
  """
  <Purpose>
    Write the delegated targets metadata, signed by the corresponding keys
    of 'keyids'.  The generated metadata file is saved to the metadata
    sub-directory of 'repository_directory'.  The generated target metadata
    will reference the paths in 'list_of_targets'.

  <Arguments>
    repository_directory:
      The path of the repository directory containing all the metadata and
      target files.

    targets_directory:
      The path of the directory containing the target files of the repository.
    
    rolename:
      The delegated role's full rolename (e.g., 'targets/unclaimed/django').

    write_partial:
      A boolean indicating if the written metadata is allowed to contain an
      invalid threshold of signatures.

  <Exceptions>
    tuf.FormatError, if any of the arguments are improperly formatted.

    tuf.UnsignedMetadataError, if a targets metadata file cannot be generated
    with a valid threshold of signatures.

  <Side Effects>
    The targets metadata object is written to a file.

  <Returns>
    None. 
  """

  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.PATH_SCHEMA.check_match(repository_directory)
  tuf.formats.PATH_SCHEMA.check_match(targets_directory)
  tuf.formats.ROLENAME_SCHEMA.check_match(rolename)
  tuf.formats.ROLEDB_SCHEMA.check_match(roleinfo) 
  tuf.formats.BOOLEAN_SCHEMA.check_match(write_partial)
  
  # The metadata version number.  Clients use the version number to determine
  # if the downloaded version is newer than the one currently trusted.
  version = roleinfo['version']
  
  # The expiration date, in UTC, of the metadata file, conformant to
  # 'tuf.formats.TIME_SCHEMA'.
  expiration = roleinfo['expires']
  
  # The corresponding keyids of the signing keys that generate the signatures
  # of the delegated metadata file.
  keyids = roleinfo['signing_keyids']
  
  # The target filepaths of the delegated role.  The paths are not verified to
  # live under the targets directory of the repository, so the caller is
  # responsible for ensuring valid target file locations.
  list_of_targets = roleinfo['paths']
  
  # The delegations of 'rolename', conformant to
  # 'tuf.formats.DELEGATIONS_SCHEMA'.
  delegations = roleinfo['delegations']
  
  # A list of signature objects to append to the generated metadata object.
  # These signatures may have been previously generated and loaded with
  # load_repository().  Conformant to 'tuf.formats.SIGNATURES_SCHEMA'.
  signatures = roleinfo['signatures']
  
  # A list of strings (e.g., 'gz') designating compression algorithms
  # to use when writing the metadata file, in addition to the uncompressed
  # version.  Conformant to 'tuf.formats.COMPRESSIONS_SCHEMA'.
  compressions = roleinfo['compressions']
 

  # Check if 'repository_directory' exists and convert it to its normalized
  # absolutized path.  Delegated metadata is written to the metadata 
  # sub-directory of 'repository_directory.
  repository_directory = _check_directory(repository_directory)
  metadata_directory = os.path.join(repository_directory,
                                    METADATA_STAGED_DIRECTORY_NAME)

  # Create the delegated metadata object.  Delegated roles are of type
  # 'tuf.formats.TARGETS_SCHEMA', same as the top-level Targets role.
  metadata_object = generate_targets_metadata(targets_directory,
                                              list_of_targets, version,
                                              expiration, delegations)

  # Delegated metadata is written to its respective directory on the
  # repository.  For example, the role 'targets/unclaimed/django' is written
  # to '{repository_directory}/metadata/targets/unlaimed/django.txt'.
  # The 'targets' directory above refers to the top-level 'targets' role,
  # which is the root parent of all targets roles.
  metadata_filepath = os.path.join(metadata_directory, rolename+'.txt')
  
  # Ensure the parent directories of 'metadata_filepath' exist, otherwise an IO
  # exception is raised if 'metadata_filepath' is written to a sub-directory.
  tuf.util.ensure_parent_dir(metadata_filepath)

  # Sign 'metadata_object' by generating signatures and storing them in the
  # 'signatures' dict key of the signable object.  The keys of 'keyids' are
  # used.
  signable = sign_metadata(metadata_object, keyids, metadata_filepath)
 
  # Add signatures that may have been loaded with load_repository(). 
  for signature in signatures:
    signable['signatures'].append(signature)
 
  # Write the metadata file, including any compressed versions, only if a
  # threshold of signatures is present.  If write_partial is True, write the
  # metadata if an insufficient threshold of signatures is present.  Writing
  # partial metadata is necessary for metadata that must be independently
  # signed.
  if tuf.sig.verify(signable, rolename) or write_partial:
    if not write_partial:
      
      # If a non-partial version is written, ensure any signatures that may
      # have been added with load_repository(), and now invalid, are discarded.
      _remove_invalid_and_duplicate_signatures(signable)
    for compression in compressions:
      write_metadata_file(signable, metadata_filepath, compression)
  
  else:
    message = 'Not enough signatures for: '+repr(metadata_filepath)
    raise tuf.UnsignedMetadataError(message)





def create_tuf_client_directory(repository_directory, client_directory):
  """
  <Purpose>
    Create a client directory structure that the 'tuf.interposition' package
    and 'tuf.client.updater' module expect of clients.  Metadata files
    downloaded from a remote TUF repository are saved to 'client_directory'.
    The Root file must initially exist before an update request can be
    satisfied.  create_tuf_client_directory() ensures the minimum metadata
    is copied and that required directories ('previous' and 'current') are
    created in 'client_directory'.  Software updaters integrating TUF may
    use the client directory created as an initial copy of the repository's
    metadadata.

  <Arguments>
    repository_directory:
      The path of the root repository directory.  The 'metadata' and 'targets'
      sub-directories should be available in 'repository_directory'.  The
      metadata files of 'repository_directory' are copied to 'client_directory'.

    client_directory:
      The path of the root client directory.  The 'current' and 'previous'
      sub-directies are created and will store the metadata files copied
      from 'repository_directory'.  'client_directory' will store metadata
      and target files downloaded from a TUF repository.
  
  <Exceptions>
    tuf.FormatError, if the arguments are improperly formatted.

    tuf.RepositoryError, if the metadata directory in 'client_directory'
    already exists.

  <Side Effects>
    Copies metadata files and directories from 'repository_directory' to
    'client_directory'.  Parent directories are created if they do not exist.

  <Returns>
    None.
  """
  
  # Do the arguments have the correct format?
  # This check ensures arguments have the appropriate number of objects and 
  # object types, and that all dict keys are properly named.
  # Raise 'tuf.FormatError' if the check fails.
  tuf.formats.PATH_SCHEMA.check_match(repository_directory)
  tuf.formats.PATH_SCHEMA.check_match(client_directory)

  # Set the absolute path of the Repository's metadata directory.  The metadata
  # directory should be the one served by the Live repository.  At a minimum,
  # the repository's root file must be copied.
  repository_directory = os.path.abspath(repository_directory)
  metadata_directory = os.path.join(repository_directory,
                                    METADATA_DIRECTORY_NAME)

  # Set the client's metadata directory, which will store the metadata copied
  # from the repository directory set above.
  client_directory = os.path.abspath(client_directory)
  client_metadata_directory = os.path.join(client_directory,
                                           METADATA_DIRECTORY_NAME)
 
  # If the client's metadata directory does not already exist, create it and
  # any of its parent directories, otherwise raise an exception.  An exception
  # is raised to avoid accidently overwritting previous metadata.
  try:
    os.makedirs(client_metadata_directory)
  except OSError, e:
    if e.errno == errno.EEXIST:
      message = 'Cannot create a fresh client metadata directory: '+ \
        repr(client_metadata_directory)+'.  Already exists.'
      raise tuf.RepositoryError(message)
    else:
      raise

  # Move all  metadata to the client's 'current' and 'previous' directories.
  # The root metadata file MUST exist in '{client_metadata_directory}/current'.
  # 'tuf.interposition' and 'tuf.client.updater.py' expect the 'current' and
  # 'previous' directories to exist under 'metadata'.
  client_current = os.path.join(client_metadata_directory, 'current')
  client_previous = os.path.join(client_metadata_directory, 'previous')
  shutil.copytree(metadata_directory, client_current)
  shutil.copytree(metadata_directory, client_previous)



if __name__ == '__main__':
  # The interactive sessions of the documentation strings can
  # be tested by running libtuf.py as a standalone module:
  # $ python libtuf.py.
  import doctest
  doctest.testmod()
