#!/usr/bin/env python

# The client first imports the 'updater.py' module, the only module the
# client is required to import.  The client will utilize a single class
# from this module.
import tuf.client.updater

# The only other module the client interacts with is 'tuf.conf'.  The
# client accesses this module solely to set the repository directory.
# This directory will hold the files downloaded from a remote repository.
tuf.conf.repository_directory = '.'

# Next, the client creates a dictionary object containing the repository
# mirrors.  The client may download content from any one of these mirrors.
# In the example below, a single mirror named 'mirror1' is defined.  The
# mirror is located at 'http://localhost:8001', and all of the metadata
# and targets files can be found in the 'metadata' and 'targets' directory,
# respectively.  If the client wishes to only download target files from
# specific directories on the mirror, the 'confined_target_dirs' field
# should be set.  In the example, the client has chosen '', which is
# interpreted as no confinement.  In other words, the client can download
# targets from any directory or subdirectories.  If the client had chosen
# 'targets1/', they would have been confined to the '/targets/targets1/'
# directory on the 'http://localhost:8001' mirror.
repository_mirrors = {'mirror1': {'url_prefix': 'http://localhost/updater/repository',
                                  'metadata_path': 'metadata',
                                  'targets_path': 'targets',
                                  'confined_target_dirs': ['']}}

# The updater may now be instantiated.  The Updater class of 'updater.py'
# is called with two arguments.  The first argument assigns a name to this
# particular updater and the second argument the repository mirrors defined
# above.
updater = tuf.client.updater.Updater('updater', repository_mirrors)

# The client calls the refresh() method to ensure it has the latest
# copies of the top-level metadata files (i.e., Root, Targets, Snapshot,
# Timestamp).
updater.refresh()

# The target file information of all the repository targets is determined next.
# Since all_targets() downloads the target files of every role, all role
# metadata is updated.
targets = updater.all_targets()

# Among these targets, determine the ones that have changed since the client's
# last refresh().  A target is considered updated if it does not exist in
# 'destination_directory' (current directory) or the target located there has
# changed.
destination_directory = '.'
updated_targets = updater.updated_targets(targets, destination_directory)

# Lastly, attempt to download each target among those that have changed.
# The updated target files are saved locally to 'destination_directory'.
for target in updated_targets:
  print target
  updater.download_target(target, destination_directory)

# Remove any files from the destination directory that are no longer being
# tracked. For example, a target file from a previous snapshot that has since
# been removed on the remote repository.
updater.remove_obsolete_targets(destination_directory)
