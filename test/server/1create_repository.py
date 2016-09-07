#!/usr/bin/env python

"""
<Program Name>
  generate.py

<Author>
  Vladimir Diaz <vladimir.v.diaz@gmail.com>

<Started>
  February 26, 2014.

<Copyright>
  See LICENSE for licensing information.

<Purpose>
  Provide a set of pre-generated key files and a basic repository that unit
  tests can use in their test cases.  The pre-generated files created by this
  script should be copied by the unit tests as needed.  The original versions
  should be preserved.  'tuf/tests/unit/repository_files/' will store the files
  generated.  'generate.py' should not require re-execution if the
  pre-generated repository files have already been created, unless they need to
  change in some way.
"""

import shutil
import datetime
import stat
import os

from tuf.repository_tool import *
import tuf.util

if os.path.isdir('repository'):
    print 'the repository already exist.'
    exit()

repository = create_new_repository('repository')

root_key_file = 'keystore/root_key'
targets_key_file = 'keystore/targets_key' 
snapshot_key_file = 'keystore/snapshot_key'
timestamp_key_file = 'keystore/timestamp_key'

# Generate and save the top-level role keys, including the delegated roles.
# The unit tests should only have to import the keys they need from these
# pre-generated key files.
# Generate public and private key files for the top-level roles, and two
# delegated roles (these number of keys should be sufficient for most of the
# unit tests).  Unit tests may generate additional keys, if needed.
generate_and_write_rsa_keypair(root_key_file, password='password')
generate_and_write_ed25519_keypair(targets_key_file, password='password')
generate_and_write_ed25519_keypair(snapshot_key_file, password='password')
generate_and_write_ed25519_keypair(timestamp_key_file, password='password')

# Import the public keys.  These keys are needed so that metadata roles are
# assigned verification keys, which clients use to verify the signatures created
# by the corresponding private keys.
root_public = import_rsa_publickey_from_file(root_key_file + '.pub')
targets_public = import_ed25519_publickey_from_file(targets_key_file + '.pub')
snapshot_public = import_ed25519_publickey_from_file(snapshot_key_file + '.pub')
timestamp_public = import_ed25519_publickey_from_file(timestamp_key_file + '.pub')

# Import the private keys.  These private keys are needed to generate the
# signatures included in metadata.
root_private = import_rsa_privatekey_from_file(root_key_file, 'password')
targets_private = import_ed25519_privatekey_from_file(targets_key_file, 'password')
snapshot_private = import_ed25519_privatekey_from_file(snapshot_key_file, 'password')
timestamp_private = import_ed25519_privatekey_from_file(timestamp_key_file, 'password')

# Add the verification keys to the top-level roles.
repository.root.add_verification_key(root_public)
repository.targets.add_verification_key(targets_public)
repository.snapshot.add_verification_key(snapshot_public)
repository.timestamp.add_verification_key(timestamp_public)

# Load the signing keys, previously imported, for the top-level roles so that
# valid metadata can be written.  
repository.root.load_signing_key(root_private)
repository.targets.load_signing_key(targets_private)
repository.snapshot.load_signing_key(snapshot_private)
repository.timestamp.load_signing_key(timestamp_private)


# Set the top-level expiration times far into the future so that
# they do not expire anytime soon, or else the tests fail.  Unit tests may
# modify the expiration  datetimes (of the copied files), if they wish.
repository.root.expiration = datetime.datetime(2030, 1, 1, 0, 0)
repository.targets.expiration = datetime.datetime(2030, 1, 1, 0, 0)
repository.snapshot.expiration = datetime.datetime(2030, 1, 1, 0, 0)
repository.timestamp.expiration = datetime.datetime(2030, 1, 1, 0, 0)

# Compress the top-level role metadata so that the unit tests have a
# pre-generated example of compressed metadata.
repository.root.compressions = ['gz']
repository.targets.compressions = ['gz']
repository.snapshot.compressions = ['gz']
repository.timestamp.compressions = ['gz']

# Create the actual metadata files, which are saved to 'metadata.staged'. 
repository.write()


