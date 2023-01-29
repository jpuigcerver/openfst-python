#!/bin/bash
set -e;

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)";

###########################################
## THIS CODE IS EXECUTED WITHIN THE HOST ##
###########################################
if [ ! -f /.dockerenv ]; then
  docker run --rm --log-driver none \
	 -v /tmp:/host/tmp \
	 -v ${SOURCE_DIR}:/host/src \
	 joapuipe/manylinux-centos7 \
	 /host/src/create_wheels.sh;
  exit 0;
fi;

#######################################################
## THIS CODE IS EXECUTED WITHIN THE DOCKER CONTAINER ##
#######################################################
set -ex;

yum install -y centos-release-scl;
yum install -y devtoolset-6-gcc*;
source /opt/rh/devtoolset-6/enable;

# Copy host source directory, to avoid changes in the host.
cp -r /host/src /tmp/src;
rm -rf /tmp/src/build /tmp/src/dist;

# This is required to build OpenFst.
yum install -y zlib-devel;

for py in cp27-cp27mu cp35-cp35m cp36-cp36m cp37-cp37m; do
  cd /tmp/src;
  export PYTHON=/opt/python/$py/bin/python;
  echo "=== Installing dependencies for $py ===";
  $PYTHON -m pip install -U pip;
  $PYTHON -m pip install -U wheel setuptools build;
  echo "=== Building for $py ==="
  $PYTHON -m build --wheel;
  echo "=== Installing for $py ===";
  cd /tmp;
  $PYTHON -m pip uninstall -y openfst_python;
  $PYTHON -m pip install openfst_python --no-index -f /tmp/src/dist --no-dependencies -v;
  echo "=== Testing for $py ===";
  $PYTHON -m unittest openfst_python.test;
done;

set +x;
ODIR="/host/tmp/openfst_python/whl";
mkdir -p "$ODIR";
readarray -t wheels < <(find /tmp/src/dist -name "*.whl");
for whl in "${wheels[@]}"; do
  whl_name="$(basename "$whl")";
  whl_name="${whl_name/-linux/-manylinux1}";
  cp "$whl" "${ODIR}/${whl_name}";
done;

echo "================================================================";
printf "=== %-56s ===\n" "Copied ${#wheels[@]} wheels to ${ODIR:5}";
echo "================================================================";
