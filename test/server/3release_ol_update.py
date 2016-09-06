#!/usr/bin/env python

import shutil

# Move the staged.metadata to 'metadata' and create the client folder.  The
# client folder, which includes the required directory structure and metadata
# files for clients to successfully load an 'tuf.client.updater.py' object.
staged_metadata_directory = 'repository/metadata.staged'
metadata_directory = 'repository/metadata'
shutil.rmtree(metadata_directory, ignore_errors=True)
shutil.copytree(staged_metadata_directory, metadata_directory)

