
https://mtazzari.github.io/galario/install.html#

install fftw-3 gcc8 py27-cpython py37-SPHINX

sudo port install py37-sphinx fftw-3 fftw-3-single py37-cython
sudo port select --set sphinx py37-sphinx
sudo port select --set cython cython37

# using HPC gcc: /usr/local/bin/gcc
rm -rf build && mkdir build && cd build
cmake -DCMAKE_INSTALL_PREFIX=/opt/galario \
      -DPython_ADDITIONAL_VERSIONS=3.7 \
      -Wno-dev \
      -DCMAKE_C_COMPILER=gcc \
      -DCMAKE_CXX_COMPILER=g++ ..

make -j12 && make install # hexa-core

pip install --user sphinx_py3doc_enhanced_theme sphinxcontrib-fulltoc

## some options of loading the Python binding of galario:

option 1 (after the "cmake" step)
    bbedit  CMakeCache.txt
    change -GALARIO_PYTHON_PKG_DIR=/Users/Rui/Library/Python/3.7/lib/python/site-packages (not need)
option 2 (may not work in a non-interative model call)
    add this to your Python startup file specified by PYTHONSTARTUP
        sys.path.insert(1,'/opt/galario/lib/python3.7/site-packages/')
option 3 (preferred)
    add this to .bashrc:
        export PYTHONPATH=$PYTHONPATH:/opt/galario/lib/python3.7/site-packages