"""
    used to test various functions
"""

from past.builtins import execfile
import numpy as np
import reikna.cluda as cluda
from reikna.cluda import any_api
import reikna.fft as cluda_fft
#import pyopencl as cl
#import pyopencl.array as cla
#import gpyfft.fft as gpyfft_fft
from reikna.cluda import dtypes, any_api
from reikna.core import Annotation, Type, Transformation, Parameter
import scipy.integrate

execfile('gmake_model_func.py')
execfile('gmake_model.py')
execfile('gmake_utils.py')
execfile('gmake_emcee.py')

def test_makekernel():

    #   this is exactly same as the 'center' method
    
    start_time = time.time()
    im=makekernel(29,21,[6.0,3.0],pa=10,mode=None)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('default',time.time()-start_time))    
    fits.writeto('test/test_makekernel_meshgrid.fits',im,overwrite=True)
    
    #   maybe a good option for some cases
    
    start_time = time.time()
    im=makekernel(29,21,[6.0,3.0],pa=10,mode='oversample')
    print("---{0:^10} : {1:<8.5f} seconds ---".format('oversample',time.time()-start_time))
    fits.writeto('test/test_makekernel_oversample.fits',im,overwrite=True)
    
    #   not preferred if you know peak is at the center of a pixel
    
    start_time = time.time()
    im=makekernel(29,21,[6.0,3.0],pa=10,mode='linear_interp')
    print("---{0:^10} : {1:<8.5f} seconds ---".format('linearinterp',time.time()-start_time))
    fits.writeto('test/test_makekernel_linearinterp.fits',im,overwrite=True)    
    
    #   this is exactly same as the meshgrid method
    
    start_time = time.time()
    im=makekernel(29,21,[6.0,3.0],pa=10,mode='center')
    print("---{0:^10} : {1:<8.5f} seconds ---".format('center',time.time()-start_time))
    fits.writeto('test/test_makekernel_center.fits',im,overwrite=True)    
    
    #   slow..slow...
    
    start_time = time.time()
    im=makekernel(29,21,[6.0,3.0],pa=10,mode='integrate')
    print("---{0:^10} : {1:<8.5f} seconds ---".format('integrate',time.time()-start_time))
    fits.writeto('test/test_makekernel_integrate.fits',im,overwrite=True)                    
    
def fftw_fftn(input_data): 
    
    #pyfftw.forget_wisdom()
    #fftn_obj = pyfftw.builders.fftn(input_data, planner_effort='FFTW_ESTIMATE')
    fftn_obj = pyfftw.builders.fftn(input_data)
    
    return fftn_obj()

def fftw_ifftn(input_data): 
    
    #pyfftw.forget_wisdom()
    #ifftn_obj = pyfftw.builders.ifftn(input_data, planner_effort='FFTW_ESTIMATE')
    ifftn_obj = pyfftw.builders.ifftn(input_data)
    
    return ifftn_obj()




#pyfftw.config.NUM_THREADS=1

def gpyfft_fftn(input_data):
    
    context = cl.create_some_context()
    queue = cl.CommandQueue(context)
    data_host = input_data
    data_gpu = cla.to_device(queue, data_host)
    transform =  gpyfft_fft.FFT(context, queue, data_gpu)
    event, = transform.enqueue(forward=True)
    event.wait()
    result_host = data_gpu.get()

    return result_host

def gpyfft_ifftn(input_data):
    
    context = cl.create_some_context()
    queue = cl.CommandQueue(context)
    data_host = input_data
    data_gpu = cla.to_device(queue, data_host)
    transform =  gpyfft_fft.FFT(context, queue, data_gpu)
    event, = transform.enqueue(forward=False)
    event.wait()
    result_host = data_gpu.get()

    return result_host


def reikna_get_complex_trf(arr):
    complex_dtype = dtypes.complex_for(arr.dtype)
    return Transformation(
        [Parameter('output', Annotation(Type(complex_dtype, arr.shape), 'o')),
        Parameter('input', Annotation(arr, 'i'))],
        """
        ${output.store_same}(
            COMPLEX_CTR(${output.ctype})(
                ${input.load_same},
                0));
        """)

def reikna_fftn_vx(input_data):
    
    #api=any_api()
    #api=cluda.cuda_api()
    api=cluda.ocl_api()
    thr = api.Thread.create()
    trf = reikna_get_complex_trf(input_data)
    fft = cluda_fft.FFT(trf.output) 
    fft.parameter.input.connect(trf, trf.output, new_input=trf.input)
    fftc=fft.compile(thr)
    data_dev = thr.to_device(input_data)
    res_dev = thr.array(arr.shape, numpy.complex64)
    fftc(data_dev,data_dev,inverse=False)

    return data_dev.get()

    
def reikna_fftn(input_data):
    
    #api=any_api()
    #api=cluda.cuda_api()
    api=cluda.ocl_api()
    thr = api.Thread.create()
    #data=input_data.astype(np.complex64)
    data=input_data
    fft=cluda_fft.FFT(data)
    fftc = fft.compile(thr)
    data_dev = thr.to_device(data)
    #res_dev = thr.empty_like(data_dev)
    #fftc(data_dev,res_dev,inverse=False)
    fftc(data_dev,data_dev,inverse=False)

    return data_dev.get()

def reikna_ifftn(input_data):
    
    #api=any_api()
    #api=cluda.cuda_api()
    api=cluda.ocl_api()
    thr = api.Thread.create()
    #data=input_data.astype(np.complex64)
    data=input_data
    fft=cluda_fft.FFT(data)
    fftc = fft.compile(thr)
    data_dev = thr.to_device(data)
    #res_dev = thr.empty_like(data_dev)
    #fftc(data_dev,res_dev,inverse=False)
    fftc(data_dev,data_dev,inverse=True)

    return data_dev.get()


def test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2):
    """
    test different options to improve convol effciency) 
    
    References:
        https://docs.scipy.org/doc/scipy/reference/tutorial/fftpack.html
        https://stackoverflow.com/questions/6365623/improving-fft-performance-in-python
        https://github.com/IntelPython/mkl_fft
        https://github.com/mperrin/webbpsf/issues/10
        https://poppy-optics.readthedocs.io/en/stable/fft_optimization.html
        https://blog.mide.com/matlab-vs-python-speed-for-vibration-analysis-free-download
        https://mathema.tician.de/the-state-of-opencl-for-scientific-computing-in-2018/
    
    Summary Note:
        + pyfftw is preferred over pyfftw3
        + opencl/reikna doesn't show clear advantages over CPU-based solutions for small arrays
            - too much overhead
        + MKL_FFT is the fastest option in general.
        + pyfft was replaced by reikna
        + turn on pyfftw.Threads doesn't help that much...
        + mkl out-performance others
        + pyfftw-build slightly better than pyfftw-interface
        + reikna
        + Loop vs. 3DFFT: 3DFFT slightly worse in single-thread test        

    pyfftw.config.NUM_THREADS = multiprocessing.cpu_count()
    pyfftw.config.NUM_THREADS = 1
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)
    test_convolve_performance(imsize=128,knsize=128,nloop=128,fftpad=False,complex_dtype=np.complex64,nd=2)
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=3)
    test_convolve_performance(imsize=1024,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)

    LOG:
    
    pyfftw.config.NUM_THREADS = multiprocessing.cpu_count()
    
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 0.02182  seconds ---
    ---fft_pad=False/scipy : 0.01356  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 0.01193  seconds ---
    ---fft_pad=False/mkl : 0.00376  seconds ---
    ---fft_pad=False/pyfftw-build : 0.02095  seconds ---
    ---fft_pad=False/reikna : 0.15106  seconds ---
    
    test_convolve_performance(imsize=128,knsize=128,nloop=128,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 1.80886  seconds ---
    ---fft_pad=False/scipy : 1.22826  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 1.15559  seconds ---
    ---fft_pad=False/mkl : 0.39774  seconds ---
    ---fft_pad=False/pyfftw-build : 1.05104  seconds ---
    ---fft_pad=False/reikna : 15.32986 seconds ---
    
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=3)
    
    ---fft_pad=False/numpy : 7.26300  seconds ---
    ---fft_pad=False/scipy : 4.91297  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 1.04028  seconds ---
    ---fft_pad=False/mkl : 0.55822  seconds ---
    ---fft_pad=False/pyfftw-build : 0.87248  seconds ---
    ---fft_pad=False/reikna : 2.00951  seconds ---
    
    test_convolve_performance(imsize=1024,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 0.48901  seconds ---
    ---fft_pad=False/scipy : 0.28967  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 0.11724  seconds ---
    ---fft_pad=False/mkl : 0.06158  seconds ---
    ---fft_pad=False/pyfftw-build : 0.10101  seconds ---
    ---fft_pad=False/reikna : 0.66387  seconds ---
    
    pyfftw.config.NUM_THREADS = 1
    
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 0.02202  seconds ---
    ---fft_pad=False/scipy : 0.01423  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 0.01028  seconds ---
    ---fft_pad=False/mkl : 0.00253  seconds ---
    ---fft_pad=False/pyfftw-build : 0.01136  seconds ---
    ---fft_pad=False/reikna : 0.16480  seconds ---
    
    test_convolve_performance(imsize=128,knsize=128,nloop=128,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 1.69174  seconds ---
    ---fft_pad=False/scipy : 1.17897  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 1.20160  seconds ---
    ---fft_pad=False/mkl : 0.37091  seconds ---
    ---fft_pad=False/pyfftw-build : 1.16632  seconds ---
    ---fft_pad=False/reikna : 15.13192 seconds ---
    
    test_convolve_performance(imsize=128,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=3)
    
    ---fft_pad=False/numpy : 7.22203  seconds ---
    ---fft_pad=False/scipy : 4.92535  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 2.38302  seconds ---
    ---fft_pad=False/mkl : 0.51912  seconds ---
    ---fft_pad=False/pyfftw-build : 2.10617  seconds ---
    ---fft_pad=False/reikna : 1.95317  seconds ---
    
    test_convolve_performance(imsize=1024,knsize=128,nloop=1,fftpad=False,complex_dtype=np.complex64,nd=2)
    
    ---fft_pad=False/numpy : 0.47751  seconds ---
    ---fft_pad=False/scipy : 0.28559  seconds ---
    ---fft_pad=False/pyfftw-interfaces : 0.17660  seconds ---
    ---fft_pad=False/mkl : 0.05815  seconds ---
    ---fft_pad=False/pyfftw-build : 0.14532  seconds ---
    ---fft_pad=False/reikna : 0.65862  seconds ---
    

    
    """
    print("\n")
    
    if  nd==2:
        im=makekernel(imsize,imsize,[6.0,6.0],pa=0)
        kn=makekernel(knsize,knsize,[15.0,5.0],pa=10)
    if  nd==3:
        im=np.ones((imsize,imsize,imsize))
        kn=np.ones((1,knsize,knsize))

    start_time = time.time()
    for i in range(nloop):
        #sm=convolve_fft(im,kn)
        # explicit default: (use fftn/ifftn rather than fft/ifft for image)
        #sm=convolve_fft(im,kn)
        # explicit default: (use fftn/ifftn rather than fft/ifft for image)
        # numpy.fft works best at 2^n
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=np.fft.fftn, ifftn=np.fft.ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/numpy',time.time()-start_time))
    fits.writeto('test/test_convolve_numpy.fits',sm,overwrite=True)    
    
    start_time = time.time()
    for i in range(nloop):
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=scipy.fftpack.fftn, ifftn=scipy.fftpack.ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/scipy',time.time()-start_time))
    fits.writeto('test/test_convolve_scipy.fits',sm,overwrite=True)    

    
    start_time = time.time()
    for i in range(nloop):
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=pyfftw.interfaces.numpy_fft.fftn, ifftn=pyfftw.interfaces.numpy_fft.ifftn)
        #               fftn=pyfftw.interfaces.scipy_fftpack.fftn, ifftn=pyfftw.interfaces.scipy_fftpack.ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/pyfftw-interfaces',time.time()-start_time))
    fits.writeto('test/test_convolve_fftw_interface.fits',sm,overwrite=True) 
    
    start_time = time.time()
    for i in range(nloop):
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=mkl_fft.fftn, ifftn=mkl_fft.ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/mkl',time.time()-start_time))
    fits.writeto('test/test_convolve_mkl.fits',sm,overwrite=True) 

    
    start_time = time.time()
    for i in range(nloop):
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=fftw_fftn, ifftn=fftw_ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/pyfftw-build',time.time()-start_time))
    fits.writeto('test/test_convolve_fftw_build.fits',sm,overwrite=True) 
             
             
    start_time = time.time()
    # my GPU only supported complex64 
    for i in range(nloop):
        sm=convolve_fft(im,kn,fft_pad=fftpad,complex_dtype=complex_dtype,
                        fftn=reikna_fftn, ifftn=reikna_ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad='+str(fftpad)+'/reikna',time.time()-start_time))
    fits.writeto('test/test_convolve_reikna.fits',sm,overwrite=True)             
    
    
    """
    #
    #    gpyfft not working properly
    # 
    
    start_time = time.time()
    for i in range(1):
        sm=convolve_fft(im,kn,fft_pad=False,complex_dtype=np.complex64,
                        fftn=gpyfft_fftn, ifftn=gpyfft_ifftn)
    print("---{0:^17} : {1:<8.5f} seconds ---".format('fft_pad=False/gpyfft',time.time()-start_time))
    fits.writeto('test/test_convolve_gpyfft.fits',sm,overwrite=True)           
    """

def test_convolve_eff():
    
    """
    convolve_fft cost: fft(im)+fft(kernel)+ifft(mutiple)
    """
    im=np.ones((100,105,105))
    kernel=np.ones((100,105,105))
    kernel_large=np.ones((100,201,201))
    kernel_small=np.ones((100,21,21))
    
    
    start_time = time.time()
    for i in range(100):
        test=convolve_fft(im[i,:,:],kernel[i,:,:])
    #   default in convolve_fft()
    #       psf_pad=True
    #       boundary='fill',fill_value=0.0
    print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop',time.time()-start_time))
    
    
    start_time = time.time()
    for i in range(100):
        test=convolve_fft(im[i,:,:],kernel[i,:,:],fft_pad=False)
    #   default in convolve_fft()
    #       psf_pad=True
    #       boundary='fill',fill_value=0.0
    print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop_nofftpad',time.time()-start_time))    
    
    #start_time = time.time()
    #for i in range(100):
    #    test=convolve_fft(im[i,:,:],kernel[i,:,:],fftn=fftn)
    #print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop',time.time()-start_time))    
    
    start_time = time.time()
    for i in range(100):
        test=convolve_fft(im[i,:,:],kernel_large[i,:,:])
    print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop_large',time.time()-start_time))    
    
    
    
    start_time = time.time()
    for i in range(100):
        test=convolve_fft(im[i,:,:],kernel_small[i,:,:])
    print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop_small',time.time()-start_time))
    

    
    start_time = time.time()
    for i in range(100):
        test=convolve_fft(im[i,:,:],kernel_large[i,:,:],fftn=fftn)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_2Dloop',time.time()-start_time))        
    
    #start_time = time.time()
    #test=convolve_fft(im,kernel[np.newaxis,0,:,:])
    #print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_fft_3D',time.time()-start_time))
    
    #start_time = time.time()
    #test=convolve(im,kernel[np.newaxis,0,:,:])
    #print("---{0:^10} : {1:<8.5f} seconds ---".format('convolve_3D',time.time()-start_time))    

def test_gmake_model_disk2d():
    
    data,hd=fits.getdata('examples/bx610/bx610.bb1.mfs.iter0.image.fits',header=True,memmap=False)
    data,hd=fits.getdata('examples/bx610/bx610.bb4.cube.iter0.image.fits',header=True,memmap=False)
    psf,phd=fits.getdata('examples/bx610/bx610.bb4.cube.iter0.psf.fits',header=True,memmap=False)
    #psf=psf[0,100,:,:]
    
    start_time = time.time()
    model=gmake_model_disk2d(hd,356.539321,12.8220179445,
                             r_eff=0.2,n=1.0,posang=20,ellip=0.5)
    print("--- %s seconds ---" % (time.time() - start_time))
    
    start_time = time.time()
    cmodel=gmake_model_simobs(model,hd)
    print("--- %s seconds ---" % (time.time() - start_time))
    
    start_time = time.time()
    cmodel_psf=gmake_model_simobs(model,hd,psf=psf)
    print("--- %s seconds ---" % (time.time() - start_time))
    
    start_time = time.time()
    cmodel_beam=gmake_model_simobs(model,hd,beam=[1.0,0.2,-30.])
    print("--- %s seconds ---" % (time.time() - start_time))    
    
    fits.writeto('test/test_model_disk2d_model.fits',model,hd,overwrite=True)
    fits.writeto('test/test_model_disk2d_cmodel.fits',cmodel,hd,overwrite=True)
    fits.writeto('test/test_model_disk2d_cmodel_psf.fits',cmodel_psf,hd,overwrite=True)
    fits.writeto('test/test_model_disk2d_cmodel_beam.fits',cmodel_beam,hd,overwrite=True)
    
def test_gmake_model_api():
    
    inp_dct=gmake_readinp('examples/bx610/bx610xy_dm_all_test.inp',verbose=False)
    dat_dct=gmake_read_data(inp_dct,verbose=False,fill_mask=True,fill_error=True)
    mod_dct=gmake_inp2mod(inp_dct)
    #pprint.pprint(mod_dct)
    start_time = time.time()
    models=gmake_model_api(mod_dct,dat_dct,verbose=False)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('apicall',time.time() - start_time))
    
    start_time = time.time()
    gmake_model_export(models,outdir='./test')
    print("---{0:^10} : {1:<8.5f} seconds ---".format('export',time.time()-start_time))
  
    m3d=SpectralCube.read('test/imod3d_bx610.bb3.cube64x64.iter0.image.fits',mode='readonly')
    m2d=SpectralCube.read('test/imod2d_bx610.bb3.cube64x64.iter0.image.fits',mode='readonly')
    m3d_m0=m3d.moment(order=0)
    m2d_m0=m2d.moment(order=0)
    m3d_m0=m3d_m0/np.max(m3d_m0.array)
    m2d_m0=m2d_m0/np.max(m2d_m0.array)
    m3d_m0.write('test/imod3d_mom0.fits',overwrite=True)
    m2d_m0.write('test/imod2d_mom0.fits',overwrite=True)
    
    #lnl,blobs=gmake_model_lnprob(fit_dct['p_start'],fit_dct,inp_dct,dat_dct,
    #                             savemodel='test/test_gmake_model_api')

    return models

def test_gmake_model_kinmspy():
    
    inp_dct=gmake_readinp('examples/bx610/bx610xy_test.inp',verbose=False)
    dat_dct=gmake_read_data(inp_dct,verbose=False,fill_mask=True,fill_error=True)
    
    mod_dct=gmake_inp2mod(inp_dct)
    obj=mod_dct['co76']
    
    start_time = time.time()
    hd=dat_dct['header@examples/bx610/bx610.bb2.cube.iter0.image.fits']
    model=gmake_model_kinmspy(hd,obj)
    print("--- %s seconds ---" % (time.time() - start_time))
    
    fits.writeto('test/test_model_kinmspy_model.fits',model,hd,overwrite=True)

def test_gmake_model_disk2d():
    
    #data,hd=fits.getdata('examples/bx610/bx610_spw25.mfs.fits',header=True,memmap=False)
    data,hd=fits.getdata('examples/bx610/bx610.bb4.cube.iter0.image.fits',header=True,memmap=False)
    psf,phd=fits.getdata('examples/bx610/bx610.bb4.cube.iter0.psf.fits',header=True,memmap=False)
    #psf=psf[0,100,:,:]
    
    start_time = time.time()
    model=gmake_model_disk2d(hd,356.539321,12.8220179445,
                             r_eff=0.2,n=1.0,posang=20,ellip=0.5)
    print("--- %s seconds ---" % (time.time() - start_time))
    
    #fits.writeto('test/test_model_disk2d.fits',model,hd,overwrite=True)
    """
    log_model=np.log(model)
    plt.figure()
    plt.imshow(np.log(model), origin='lower', interpolation='nearest',
           vmin=np.min(log_model), vmax=np.max(log_model))
    plt.xlabel('x')
    plt.ylabel('y')
    cbar = plt.colorbar()
    cbar.set_label('Log Brightness', rotation=270, labelpad=25)
    cbar.set_ticks([np.min(log_model),np.max(log_model)], update_ticks=True)
    plt.savefig('test/test_model_disk2d.eps')
    """
def test_wcs2pix():
    
    data,header=fits.getdata('examples/bx610/bx610.bb1.cube.iter0.image.fits',header=True,memmap=False)
    xypos=[356.539321,12.8220179445]
    px,py,pz,ps=(WCS(header).wcs_world2pix(xypos[0],xypos[1],0,0,0))
    print(xypos)
    print(px,py)

def test_mcspeed():
    
    inp_dct=gmake_readinp('examples/bx610/bx610xy_dm_all_test.inp',verbose=False)
    dat_dct=gmake_read_data(inp_dct,verbose=True,fill_mask=True,fill_error=True)
    fit_dct,sampler=gmake_emcee_setup(inp_dct,dat_dct)
    gmake_emcee_iterate(sampler,fit_dct,nstep=1,mctest=True)


def imcontsub(fn):
    
    cube=SpectralCube.read(fn,mode='readonly')
    spectral_axis = cube.spectral_axis
    good_channels=  ((spectral_axis > 250.000*u.GHz) & (spectral_axis < 250.964*u.GHz)) | \
                    ((spectral_axis > 251.448*u.GHz) & (spectral_axis < 251.847*u.GHz)) | \
                    ((spectral_axis > 252.246*u.GHz) & (spectral_axis < 253.000*u.GHz))
    masked_cube = cube.with_mask(good_channels[:, np.newaxis, np.newaxis])
    med = masked_cube.median(axis=0)
    cube_mean = masked_cube.mean(axis=0)  
    cube_submean=cube-cube_mean
    cube.write('test_cube.fits',overwrite=True)
    cube_submean.write('test_cube_submean.fits',overwrite=True)
    cube_mean.write('test_cube_mean.fits',overwrite=True)
    m0=cube_submean.moment(order=0)
    m0.write('test_cube_submean_mom0.fits',overwrite=True)
    
def test_sersic1d_sample():
    

    plt.clf()
    #fig,ax=plt.figure(figsize=(8,8)) 
    
    fig,ax=plt.subplots(1,1,figsize=(16,8))
    s1 = Sersic1D(amplitude=1, r_eff=0.12)
    r=np.arange(-0.72, 0.72, .04)
    r_fine=np.arange(-0.7, 0.7, .0001)
    r_test=np.arange(-0.6, 0.6, .12)
    print(r)
    for n in np.arange(1, 2):
         s1.n = n
         ax.plot(r, s1(np.abs(r)),color='blue')
         #ax.plot(r_test, s1(np.abs(r_test)),drawstyle='steps-mid',color='blue')
         ax.plot(r_test, s1(np.abs(r_test)),color='red',drawstyle='steps-mid')
         ax.plot(r_fine, s1(np.abs(r_fine)),color='gray')
         
    #plt.axis([1e-1, 30, 1e-2, 1e3])
    ax.set_xlabel('radius')
    ax.set_ylabel('Surface Brightness')
    ax.text(.25, 1.5, 'n=1')
    ax.text(.25, 300, 'n=10')

    fig.savefig('test/test_sersic1d_sample.pdf')
    
def test_make_cloudlet():
    
    seed=[100,101,102,103]
    nSamps=100000
    

    

    
    ##########
    #   good enough (better at flux conservatition)
    ##########
    
    x,y = np.meshgrid(np.arange(50), np.arange(50))
    mod = Sersic2D(amplitude=1.0,r_eff=0.20/0.04,n=1,x_0=25,y_0=25,
               ellip=0,theta=0)
    dmodel2d=discretize_model(mod,(0,50),(0,50),mode='oversample')
    dmodel2d=dmodel2d/np.max(dmodel2d)
    fits.writeto('test/test_make_cloudlet_dmodel.fits',dmodel2d,overwrite=True)
    
    ##########
    #   good enough
    ##########
    
    x,y = np.meshgrid(np.arange(50), np.arange(50))
    mod = Sersic2D(amplitude=1.0,r_eff=0.20/0.04,n=1,x_0=25,y_0=25,
               ellip=0,theta=0)
    model2d=mod(x,y)
    model2d=model2d/np.max(model2d)
    fits.writeto('test/test_make_cloudlet_model.fits',model2d,overwrite=True)
    
    
    #########
    #   original
    #########
    
    sbRad=np.arange(0,1,0.12)
    mod = Sersic1D(amplitude=1.0,r_eff=0.20,n=1.0)
    sbProf=mod(sbRad)
    
    #Randomly generate the radii of clouds based on the distribution given by the brightness profile
    px = np.zeros(len(sbProf))
    sbProf = sbProf * (2 * np.pi * abs(sbRad))  
    px = np.cumsum(sbProf)
    px /= max(px)           
    rng1 = np.random.RandomState(seed[0])            
    pick = rng1.random_sample(nSamps)  
    interpfunc = interpolate.interp1d(px,sbRad, kind='linear')
    r_flat = interpfunc(pick)
    
    r_3d=r_flat
    
    #Generates a random phase around the galaxy's axis for each cloud
    rng2 = np.random.RandomState(seed[1])        
    phi = rng2.random_sample(nSamps) * 2 * np.pi        
    
    theta = np.arccos(0 / r_3d)
    xPos = ((r_3d * np.cos(phi) * np.sin(theta)))                                                        
    yPos = ((r_3d * np.sin(phi) * np.sin(theta)))
    
    xybin,xedge,yedge=np.histogram2d(xPos,yPos,bins=50,range=[[-1, 1], [-1, 1]])
    fits.writeto('test/test_make_cloudlet_xybin_undersample.fits',xybin/np.max(xybin),overwrite=True)
    

    #########
    #  hacked (oversample) [ clode to the actual model)
    #########
    
    sbRad=np.arange(0,1,0.04)
    mod = Sersic1D(amplitude=1.0,r_eff=0.20,n=1.0)
    sbProf=mod(sbRad)
    
    #Randomly generate the radii of clouds based on the distribution given by the brightness profile
    px = np.zeros(len(sbProf))
    sbProf = sbProf * (2 * np.pi * abs(sbRad))  
    px = np.cumsum(sbProf)
    px /= max(px)           
    rng1 = np.random.RandomState(seed[0])            
    pick = rng1.random_sample(nSamps)  
    interpfunc = interpolate.interp1d(px,sbRad, kind='linear')
    r_flat = interpfunc(pick)
    
    r_3d=r_flat
    
    #Generates a random phase around the galaxy's axis for each cloud
    rng2 = np.random.RandomState(seed[1])        
    phi = rng2.random_sample(nSamps) * 2 * np.pi        
    
    theta = np.arccos(0 / r_3d)
    xPos = ((r_3d * np.cos(phi) * np.sin(theta)))                                                        
    yPos = ((r_3d * np.sin(phi) * np.sin(theta)))
    
    xybin,xedge,yedge=np.histogram2d(xPos,yPos,bins=50,range=[[-1, 1], [-1, 1]])
    fits.writeto('test/test_make_cloudlet_xybin_okaysample.fits',xybin/np.max(xybin),overwrite=True)    
    
    #########
    #  hacked (oversample) [ clode to the actual model)
    #########
    
    sbRad=np.arange(0,1,0.01)
    mod = Sersic1D(amplitude=1.0,r_eff=0.20,n=1.0)
    sbProf=mod(sbRad)
    
    #Randomly generate the radii of clouds based on the distribution given by the brightness profile
    px = np.zeros(len(sbProf))
    sbProf = sbProf * (2 * np.pi * abs(sbRad))  
    px = np.cumsum(sbProf)
    px /= max(px)           
    rng1 = np.random.RandomState(seed[0])            
    pick = rng1.random_sample(nSamps)  
    interpfunc = interpolate.interp1d(px,sbRad, kind='linear')
    r_flat = interpfunc(pick)
    
    r_3d=r_flat
    
    #Generates a random phase around the galaxy's axis for each cloud
    rng2 = np.random.RandomState(seed[1])        
    phi = rng2.random_sample(nSamps) * 2 * np.pi        
    
    theta = np.arccos(0 / r_3d)
    xPos = ((r_3d * np.cos(phi) * np.sin(theta)))                                                        
    yPos = ((r_3d * np.sin(phi) * np.sin(theta)))
    
    xybin,xedge,yedge=np.histogram2d(xPos,yPos,bins=50,range=[[-1, 1], [-1, 1]])
    fits.writeto('test/test_make_cloudlet_xybin_oversample.fits',xybin/np.max(xybin),overwrite=True)    
    
    
    #######
    #   improved
    #######
    
    plt.clf()
    fig,ax=plt.subplots(1,1,sharex=True,figsize=(12,12))
    ax.plot(xPos,yPos,'+')
    fig.savefig('test/test_make_cloudlet.pdf')
    
def test_cog_precision():    
    
    # https://docs.scipy.org/doc/scipy/reference/integrate.html#module-scipy.integrate
    
    plt.clf()
    fig,ax=plt.subplots(1,1,sharex=True,figsize=(20,20))
    
    #   precise integration
    step=0.00001
    sbRad=np.arange(0,1,step)
    mod = Sersic1D(amplitude=1.0,r_eff=0.12,n=1.0)
    sbProf=mod(sbRad)
    
    start_time = time.time()
    csbProf_trapz=scipy.integrate.cumtrapz(sbProf*2.0*np.pi*sbRad,sbRad,initial=0)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumtrapz',time.time()-start_time)) 
    start_time = time.time()
    csbProf_sum = np.cumsum(sbProf * (2. * np.pi * abs(sbRad))*step)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumsum',time.time()-start_time))      

    ax.plot(sbRad,csbProf_trapz,color='black')
    ax.plot(sbRad,csbProf_sum,'-',color='black')
    
    #   1/10=r_e sampling (cumtrapz better)
    step=0.012
    sbRad=np.arange(0,1,step)
    mod = Sersic1D(amplitude=1.0,r_eff=0.12,n=1.0)
    sbProf=mod(sbRad)
    
    start_time = time.time()
    csbProf_trapz=scipy.integrate.cumtrapz(sbProf*2.0*np.pi*sbRad,sbRad,initial=0)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumtrapz',time.time()-start_time)) 

    start_time = time.time()
    csbProf_sum = np.cumsum(sbProf * (2. * np.pi * abs(sbRad))*step)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumsum',time.time()-start_time))      

    ax.plot(sbRad,csbProf_trapz,color='cyan')
    ax.plot(sbRad,csbProf_sum,'--',color='cyan')    
    
    #   even worse (both failed)
    step=0.04
    sbRad=np.arange(0,1,step)
    mod = Sersic1D(amplitude=1.0,r_eff=0.12,n=1.0)
    sbProf=mod(sbRad)
    
    start_time = time.time()
    csbProf_trapz=scipy.integrate.cumtrapz(sbProf*2.0*np.pi*sbRad,sbRad,initial=0)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumtrapz',time.time()-start_time)) 

    start_time = time.time()
    csbProf_sum = np.cumsum(sbProf * (2. * np.pi * abs(sbRad))*step)
    print("---{0:^10} : {1:<8.5f} seconds ---".format('cumsum',time.time()-start_time))      

    ax.plot(sbRad,csbProf_trapz,color='red')
    ax.plot(sbRad,csbProf_sum,'--',color='red')
  
    
    
#     step_fine=0.001
#     sbRad_fine=np.arange(0,1,step_fine)
#     sbProf_fine=mod(sbRad_fine)
#     
#     start_time = time.time()
#     x_fine=sbRad_fine
#     y_fine=scipy.integrate.cumtrapz(sbProf_fine*2.0*np.pi*sbRad_fine,sbRad_fine,initial=0)
#     print("---{0:^10} : {1:<8.5f} seconds ---".format('cumtrapz',time.time()-start_time)) 
#     
#     ax.plot(x,y1,color='red')
#     ax.plot(x,y1-y)
#     ax.plot(x_fine,y_fine,color='black')
    
    fig.savefig('test/test_cog_precision.pdf')
    
    #print(y)
if  __name__=="__main__":
    
    #pass

    #imcontsub('examples/bx610/bx610.bb2.cube64x64.iter0.image.fits')
    #test_sersic1d_sample()
    #test_gmake_model_api()
    
    #test_makekernel()
    #test_make_cloudlet()
    #%timeit -n 100 for _ in range(10): True
    #   %timeit -n 10 "np.zeros((100,100,100)"
    #   %timeit -n 10 "np.empty((100,100,100)"
    #test_gmake_model_disk2d()
    #test_gmake_model_kinmspy()
    models=test_gmake_model_api()
    #test_cog_precision()
    #test_wcs2pix()
    
    
    
    #test_mcspeed()

    








    
