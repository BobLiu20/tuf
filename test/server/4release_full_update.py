#!/usr/bin/env python

from tuf.repository_tool import *
import shutil

# Create the client files (required directory structure and minimal metadata)
# required by the 'tuf.interposition' and 'tuf.client.updater.py' updaters.
shutil.rmtree('client', ignore_errors=True)
shutil.copytree('repository/targets/', 'client')
create_tuf_client_directory('repository', 'client')

