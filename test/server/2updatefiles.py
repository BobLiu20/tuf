from tuf.repository_tool import *
import os

# Load the repository created in the previous section.  This repository so far
# contains metadata for the top-level roles, but no target paths are yet listed
# in targets metadata.
repository = load_repository("./repository/")

if False:
    # get_filepaths_in_directory() returns a list of file paths in a directory.  It can also return
    # files in sub-directories if 'recursive_walk' is True.
    list_of_targets = repository.get_filepaths_in_directory("./repository/targets/",
                                                            recursive_walk=False, followlinks=True) 

    # Add the list of target paths to the metadata of the top-level Targets role.
    # Any target file paths that might already exist are NOT replaced.
    # add_targets() does not create or move target files on the file system.  Any
    # target paths added to a role must be relative to the targets directory,
    # otherwise an exception is raised.
    repository.targets.add_targets(list_of_targets)
else:
    repository.targets.update_targets_auto()

# Individual target files may also be added to roles, including custom data
# about the target.  In the example below, file permissions of the target
# (octal number specifying file access for owner, group, others (e.g., 0755) is
# added alongside the default fileinfo.  All target objects in metadata include
# the target's filepath, hash, and length.
# target3_filepath = "/path/to/repository/targets/file3.txt"
# octal_file_permissions = oct(os.stat(target3_filepath).st_mode)[4:]
# custom_file_permissions = {'file_permissions': octal_file_permissions}
# repository.targets.add_target(target3_filepath, custom_file_permissions)

private_targets_key =  import_ed25519_privatekey_from_file("keystore/targets_key", password='password')
repository.targets.load_signing_key(private_targets_key)
private_snapshot_key =  import_ed25519_privatekey_from_file("keystore/snapshot_key", password='password')
repository.snapshot.load_signing_key(private_snapshot_key)
private_timestamp_key =  import_ed25519_privatekey_from_file("keystore/timestamp_key", password='password')
repository.timestamp.load_signing_key(private_timestamp_key)

repository.write()

