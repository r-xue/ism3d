Install casacore 3.1.0:

    sudo port install boost +python37
    #sudo port install boost +python37 -no_static
    rm -rf build && mkdir build && cd build
    export CFLAGS=-I/opt/local/include
    export LDFLAGS=-L/opt/local/lib
    export LD_LIBRARY_PATH=-L/opt/local/lib
    #make sure xcode update-to-date
    #   likely you want to use the Apple cc instead (so don;t use the below line and make sure > port seletc gcc none)
    #   export CC=/opt/local/bin/gcc 
    
    #   use xcode cc/c++ rather than the ones from macports
    -- Check for working C compiler: /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/cc -- works
    -- Check for working CXX compiler: /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/c++ -- works

    
    cmake -DUSE_FFTW3=ON \
        -DUSE_OPENMP=ON \
        -DUSE_THREADS=ON \
        -DBUILD_PYTHON=OFF \
        -DBUILD_PYTHON3=ON \
        -DDATA_DIR=/Applications/CASA.app/Contents/data \
        -DCMAKE_INSTALL_PREFIX=/opt/casacore \
        -DBOOST_LIBRARYDIR=/opt/local/lib \
        -DPYTHON3_EXECUTABLE=/opt/local/bin/python3 \
        -DPYTHON3_LIBRARIES=/opt/local/Library/Frameworks/Python.framework/Versions/3.7/lib/libpython3.7.dylib \
        -DPYTHON3_NUMPY_INCLUDE_DIRS= /Users/Rui/Library/Python/3.7/lib/python/site-packages/numpy/core/include \
        ..
        
        #-DBUILD_DEPRECATED=ON \        
        #-DUSE_HDF5=ON \
        #-DBUILD_PYTHON=ON \        
    make -j8
    make install

########################


    otool -L /opt/local/lib/libboost_python3-mt.dylib
      /opt/local/lib/libboost_python3-mt.dylib:
    	/opt/local/lib/libboost_python3-mt.dylib (compatibility version 0.0.0, current version 0.0.0)
    	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 400.9.4)
    	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1252.200.5)

    since libboost_python3 was compoiled with libc++.1, the other needs to be the same
    
    
    
    otool -L /opt/local/lib/libboost_python3-mt.dylib
    




########## FROM MIRAID/borrow


if you don't see a directory 'casacore' or some version 'casacore-1.5'
here, it probably means you did not get this added package for
MIRIAD. It is only needed if you want to build the carmafiller program
to convert miriad visibility files into a CASA Measurement Set. Currently
the installation is manual, the instructions are below, but have not
been tested on many machines.    

They have been tested on:
     ubuntu 12.04 LTS, 14.04 LTS
     Scientific Linux 6.4

See $MIR/install/install.carmafiller for the current install script.  The text
below are guidelines to alternative paths to success



First some optional prep work:


1a) install cfitsio if your system doesn't have it, casacore needs it
   Here is an example for version 3.340 , see
   http://heasarc.gsfc.nasa.gov/fitsio/   for the latest updates
    (ubuntu:   sudo apt-get install cfitsio3)

cd $MIR/borrow

wget ftp://heasarc.gsfc.nasa.gov/software/fitsio/c/cfitsio_latest.tar.gz
tar zxf cfitsio$v.tar.gz 
  or
curl ftp://heasarc.gsfc.nasa.gov/software/fitsio/c/cfitsio_latest.tar.gz | tar zxf -

cd cfitsio
./configure --prefix=$MIR/opt
make 
make install

1b) If your system does not come with lapack/blas, or flex/bison, you
    may also find yourself in having to install those.
    You also need the 'cmake' tool.
    gsl is a new dependency that was added recently. (NRAO version only for now)
    wcslib is also needed, but since MIRIAD now needs this, we're going
    to assume that we can use this version, since it comes included.
    HDF5 and fftw3 are both optional, and currently not used in this 
    MIRIAD build.
    (ubuntu: liblapack-dev libblas-dev)

    CMAKE:
    curl http://www.cmake.org/files/v2.8/cmake-2.8.10.2.tar.gz | tar zxf -
    cd cmake-2.8.10.2/
    ./configure --prefix=$MIR/opt
    make
    make install


1c) If you plan to install carmafiller, do this:

    cd $MIR/borrow
    cvs co importmiriad
    (cd importmiriad/miriad/ ; ln -s implement/Filling/)

    and any CVS updates with
    (cd $MIR/borrow/importmiriad; cvs update)

2) install casacore, note the version number, and note if you 
   need the extra -DCFITSIO_ROOT_DIR=$MIR/opt (see item 1)

cd $MIR/borrow


if (1) then
  # grab the stable google code version (rev 21337)
  # 21430 on 24-apr-2014 w/ Ubuntu 14.04
  svn -q co http://casacore.googlecode.com/svn/tags/casacore-1.5.0
    (about 111MB)
  cd casacore-1.5.0
  # april-2014: the trunk now fails on U14, the nrao-nov12 branch is ok.
  # svn switch http://casacore.googlecode.com/svn/branches/nrao-nov12/
else
  # or something like the NRAO version [which doesn't work yet for me]
  svn co https://svn.cv.nrao.edu/svn/casa/branches/stable-2013-03/casacore
  # or the google code again (rev 21347 or later)
  # svn co http://casacore.googlecode.com/svn/trunk/ casacore
  cd casacore
endif

# patch up to prepare for carmafiller
ln -s ../importmiriad/miriad
cp CMakeLists.txt CMakeLists.txt-orig
sed "s/components/components miriad/" CMakeLists.txt-orig  > CMakeLists.txt
diff CMakeLists.txt-orig CMakeLists.txt
# you should only see one line where miriad was added... if not, might be broken

mkdir build
cd build
if (-e $MIR/opt/lib/libcfitsio.a) then
  cmake -DWCSLIB_ROOT_DIR=$MIR/opt \
      -DCMAKE_INSTALL_PREFIX=$MIR/opt/casa \
      -DDATA_DIR=$MIR/opt/casa/data \
      -DCFITSIO_ROOT_DIR=$MIR/opt \
      ..
else
  cmake -DWCSLIB_ROOT_DIR=$MIR/opt \
      -DCMAKE_INSTALL_PREFIX=$MIR/opt/casa \
      -DDATA_DIR=$MIR/opt/casa/data \
      ..
endif

make -j8
make install

"make"  takes about 50 mins. on nemo2, but -j8 will go a lot faster.  12 mins on chara.

Any CVS updates to e.g. importmiriad, do this:
    (cd $MIR/borrow/importmiriad; cvs update)
    (cd $MIR/borrow/casacore-1.5.0/build; make install)

3) install CASA measures data (ephemeris, dUT1 tables etc.)

cd $MIR/opt/casa
wget  ftp://ftp.atnf.csiro.au/pub/software/measures_data/measures_data.tar.bz2
tar jxf measures_data.tar.bz2
    (about 8MB, expanding into 22 MB)

    or simply:

curl ftp://ftp.atnf.csiro.au/pub/software/measures_data/measures_data.tar.bz2 | tar jxf -


See also https://safe.nrao.edu/wiki/bin/view/Software/ObtainingCasaDataRepository 
for potential updates to this developing story.



### update data repo

cd $MIR/opt/casa
svn co https://svn.cv.nrao.edu/svn/casa-data/trunk/ephemerides data/ephemerides
svn co https://svn.cv.nrao.edu/svn/casa-data/trunk/geodetic    data/geodetic

the next time you can simply update this data tree as follows:

cd $MIR/opt/casa/data/ephemerides
svn update
cd $MIR/opt/casa/data/geodetic
svn update

And it will report what revision (version) number you have. This might be important
information if you ever have an issue with 


On a MAC you'll need to wrap line 158.. of the CMakeLists.txt file 
otherwise a bug on C compiler on MAC will silence cmake.
if(USE_THREADS)
....
endif(USE_THREADS)