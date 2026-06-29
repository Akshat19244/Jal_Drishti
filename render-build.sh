#!/bin/bash
# Build script for Render to handle Git LFS files

echo "Installing Git LFS..."
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | bash
apt-get install git-lfs -y

echo "Pulling Git LFS files..."
git lfs install
git lfs pull

echo "Build complete!"
