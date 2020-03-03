from .model_func import *
from .model_dynamics import *
from .io import *
from .meta import xymodel_header

#from galario.double import get_image_size
#from galario.double import sampleImage
#from galario.double import chi2Image
from galario.single import get_image_size

logger = logging.getLogger(__name__)

import scipy.constants as const

from astropy.modeling.models import Gaussian2D

from memory_profiler import profile


def model_api(mod_dct,dat_dct,nsamps=100000,decomp=False,verbose=False):
    """
    use model properties (from mod_dct) and data metadata info (from dat_dct) to
    create a data model
    """
    
    models=model_init(mod_dct,dat_dct,decomp=decomp,verbose=verbose)
    model_fill(models,decomp=decomp,nsamps=nsamps,verbose=verbose)
    model_simobs(models,decomp=decomp,verbose=verbose)

    return models


def model_init(mod_dct,dat_dct,decomp=False,verbose=False,save_uvmodel=True):
    """
    create model container 
        this function can be ran only once before starting fitting iteration, so that
        the memory allocation/ allication will happen once during a fitting run.

    notes on evaluating efficiency:
    
        While building the intrinsic data-model from a physical model can be expensive,
        the simulated observation (2D/3D convolution) is usually the bottle-neck.
        
        some tips to improve the effeciency:
            + exclude empty (masked/flux=0) region for the convolution
            + joint all objects in the intrinsic model before the convolution, e.g.
                overlapping objects, lines
            + use to low-dimension convolution when possible (e.g. for the narrow-band continumm) 
            
        before splitting line & cont models:
            --- apicall   : 2.10178  seconds ---
        after splitting line & cont models:
            --- apicall   : 0.84662  seconds ---
    note: imod2d                : Hold emission componnets with Frequency-Dependent Spatial Distribution
          imod3d                : Hold emission conponents with Frequency-Dependent Spatial Distribution
          imodel=imod2d+imod3d  : We always keep a copy of imod2d and imod3d to improve the effeicnecy in simobs() 

          uvmodel: np.complex64
           imodel:  np.float32
                              
    """
    
    if  verbose==True:
        start_time = time.time()
            
    models={'mod_dct':mod_dct.copy()}
                
    for tag in list(mod_dct.keys()):
        
        obj=models['mod_dct'][tag]
        
        if  verbose==True:
            print("+"*40); print('@',tag); print('type:',obj['type']) ; print("-"*40)

        if  'vis' in mod_dct[tag].keys():
            
            vis_list=mod_dct[tag]['vis'].split(",")
            
            for vis in vis_list:
                
                if  'type@'+vis not in models.keys():
                    
                    #   pass the data reference (no memory penalty)
                    
                    
                    models['type@'+vis]=dat_dct['type@'+vis]
                    
                    if  save_uvmodel==True:
                        models['data@'+vis]=dat_dct['data@'+vis]
                        models['weight@'+vis]=dat_dct['weight@'+vis]   
                        models['uvw@'+vis]=dat_dct['uvw@'+vis]
                    
                    models['chanfreq@'+vis]=dat_dct['chanfreq@'+vis]
                    models['flag@'+vis]=dat_dct['flag@'+vis]
                    models['chanwidth@'+vis]=dat_dct['chanwidth@'+vis]
                    models['phasecenter@'+vis]=dat_dct['phasecenter@'+vis]
                    wv=np.mean(const.c/models['chanfreq@'+vis].to_value(u.Hz)) # in meter
                    
                    #
                    ant_size=12.0 # hard coded in meter
                    f_max=2.0
                    f_min=3.0/3.0
                    """
                    f_max: determines the UV grid size, or set a image cell-size upper limit
                           a valeu of >=2 would be a safe choice
                    f_min: set the UV cell-size upper limit, or a lower limit of image FOV.                            
                           a value of >=3 would be translated into a FOV lager than >=3 of interfeormetry sensitive scale
                    PB:    primary beam size, help set a lower limit of FOV
                           however, in terms of imaging quality metric, this is not crucial
                    The rule of thumbs are:
                        * make sure f_max and f_min are good enought that all spatial frequency information is presented in
                        the reference models
                        * the FOV is large enough to covert the object.
                        * keep the cube size within the memory limit
                    """
                    nxy, dxy = get_image_size(dat_dct['uvw@'+vis][:,0]/wv, dat_dct['uvw@'+vis][:,1]/wv,
                                              PB=1.22*wv/ant_size*0.0,f_max=f_max,f_min=f_min,
                                              verbose=False)
                    #print("-->",nxy,np.rad2deg(dxy)*60.*60.,vis)
                    #print(np.rad2deg(dxy)*60.*60,0.005,nxy)
                    # note: if dxy is too large, uvsampling will involve extrapolation which is not stable.
                    #       if nxy is too small, uvsampling should be okay as long as you believe no stucture-amp is above that scale.
                    #          interplate is more or less stable.  
                    #dxy=np.deg2rad(0.02/60/60)
                    #nxy=128
                    
                    header=xymodel_header.copy()
                    header['NAXIS1']=nxy
                    header['NAXIS2']=nxy
                    header['NAXIS3']=np.size(models['chanfreq@'+vis])
                    #header['CRVAL1']=models['phasecenter@'+vis][0].to_value(u.deg)
                    #header['CRVAL2']=models['phasecenter@'+vis][1].to_value(u.deg)
                    header['CRVAL1']=obj['xypos'].ra.to_value(u.deg)
                    header['CRVAL2']=obj['xypos'].dec.to_value(u.deg)
                                         
                    crval3=models['chanfreq@'+vis].to_value(u.Hz)
                    if  not np.isscalar(crval3):
                        crval3=crval3[0]
                    header['CRVAL3']=crval3
                    header['CDELT1']=-np.rad2deg(dxy)
                    header['CDELT2']=np.rad2deg(dxy)
                    header['CDELT3']=np.mean(dat_dct['chanwidth@'+vis].to_value(u.Hz))   
                    header['CRPIX1']=np.floor(nxy/2)+1
                    header['CRPIX2']=np.floor(nxy/2)+1
                    
                    models['header@'+vis]=header.copy()
                    
                    models['pbeam@'+vis]=((makepb(header)).astype(np.float32))[np.newaxis,np.newaxis,:,:]
                    naxis=(header['NAXIS4'],header['NAXIS3'],header['NAXIS2'],header['NAXIS1'])
                    models['imod3d@'+vis]=np.zeros(naxis,dtype=np.float32)     # 1 * nz * ny * nx
                    #naxis=(header['NAXIS4'],1,header['NAXIS2'],header['NAXIS1'])
                    models['imod2d@'+vis]=np.zeros(naxis,dtype=np.float32)     # 1 * 1  * ny * nx
                    
                    
                    if  save_uvmodel==True:
                        models['uvmodel@'+vis]=np.zeros((models['data@'+vis].shape)[0:2],
                                                    dtype=models['data@'+vis].dtype,
                                                    order='F')
                    if  decomp==True:
                        models['uvmod2d@'+vis]=np.zeros((models['data@'+vis].shape)[0:2],
                                                    dtype=models['data@'+vis].dtype,
                                                    order='F')                        
                        models['uvmod3d@'+vis]=np.zeros((models['data@'+vis].shape)[0:2],
                                                    dtype=models['data@'+vis].dtype,
                                                    order='F')
                        
                obj['pmodel']=None
                obj['pheader']=None
                if  'pmodel@'+tag in dat_dct.keys():
                    obj['pmodel']=dat_dct['pmodel@'+tag]
                    obj['pheader']=dat_dct['pheader@'+tag]
                                        

                    
        if  'image' in mod_dct[tag].keys():
            
            image_list=mod_dct[tag]['image'].split(",")
            
            for image in image_list:
                                
                if  'data@'+image not in models.keys():
                    
                    #test_time = time.time()
                    models['header@'+image]=dat_dct['header@'+image]
                    models['data@'+image]=dat_dct['data@'+image]
                    models['error@'+image]=dat_dct['error@'+image]   
                    models['mask@'+image]=dat_dct['mask@'+image]
                    models['type@'+image]=dat_dct['type@'+image]
                    
                    if  'sample@'+image in dat_dct.keys():
                        models['sample@'+image]=dat_dct['sample@'+image]
                    else:
                        models['sample@'+image]=None                                        
                    
                    if  'psf@'+image in dat_dct.keys():
                        models['psf@'+image]=dat_dct['psf@'+image]
                    else:
                        models['psf@'+image]=None
                    naxis=models['data@'+image].shape
                    if  len(naxis)==3:
                        naxis=(1,)+naxis
                    models['imodel@'+image]=np.zeros(naxis)
                    models['cmodel@'+image]=np.zeros(naxis)
                    #   save 2d objects (even it has been broadcasted to 3D for spectral cube)
                    #   save 3D objects (like spectral line emission from kinmspy/tirific)
                    models['imod2d@'+image]=np.zeros(naxis)
                    models['imod3d@'+image]=np.zeros(naxis)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('import:'+image,time.time() - test_time))
      
                obj['pmodel']=None
                obj['pheader']=None
                if  'pmodel@'+tag in dat_dct.keys():
                    obj['pmodel']=dat_dct['pmodel@'+tag]
                    obj['pheader']=dat_dct['pheader@'+tag]      
                
    if  verbose==True:            
        print(">>>>>{0:^10} : {1:<8.5f} seconds ---\n".format('initialize-total',time.time() - start_time))
                
    return models



#@profile
def model_fill(models,nsamps=100000,decomp=False,verbose=False):
    """
    create reference/intrinsic models and fill them into the model container

    Notes (on evaluating efficiency):
    
        While building the intrinsic data-model from a physical model can be expensive,
        the simulated observation (2D/3D convolution or UV sampling) is usually the bottle-neck.
        
        some tips to improve the effeciency:
            + exclude empty (masked/flux=0) region for the convolution
            + joint all objects in the intrinsic model before the convolution, e.g.
                overlapping objects, lines
            + use to low-dimension convolution when possible (e.g. for the narrow-band continumm) 
            
        before splitting line & cont models:
            --- apicall   : 2.10178  seconds ---
        after splitting line & cont models:
            --- apicall   : 0.84662  seconds ---
    
    
    """
    
    if  verbose==True:
        start_time = time.time()    

    mod_dct=models['mod_dct']
    
    #   add ref models OBJECT by OBJECT
                
    for tag in list(mod_dct.keys()):

        #   skip if no "type" or the item is not a physical model
        
        obj=mod_dct[tag]
        
        if  verbose==True:
            print("+"*40); print('@',tag); print('type:',obj['type']) ; print("-"*40)

        if  'vis' in mod_dct[tag].keys():
            
            vis_list=mod_dct[tag]['vis'].split(",")
            
            for vis in vis_list:
                
                test_time = time.time()
                
                if  'disk2d' in obj['type'].lower():
                    #test_time = time.time()

                    model_disk2d(models['header@'+vis],obj,
                                        model=models['imod2d@'+vis],
                                        factor=5)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('fill:  '+tag+'-->'+vis+' disk2d',time.time() - test_time))
                    #print(imodel.shape)
                    #models['imod2d@'+vis]+=imodel
                    #models['imodel@'+vis]+=imodel
                    
                if  'disk3d' in obj['type'].lower():
                    #pprint(obj)
                    #test_time = time.time()              
                    imodel_prof=model_disk3d(models['header@'+vis],obj,
                                                    model=models['imod3d@'+vis],
                                                    nsamps=nsamps,fixseed=False,mod_dct=mod_dct)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('fill:  '+tag+'-->'+vis+' disk3d',time.time() - test_time))
                    #print(imodel.shape)
                    #models['imod3d@'+vis]+=imodel
                    models['imod3d_prof@'+tag+'@'+vis]=imodel_prof.copy()
                    #models['imodel@'+vis]+=imodel     
                    
        if  'image' in mod_dct[tag].keys():
            
            image_list=mod_dct[tag]['image'].split(",")
            
            for image in image_list:
                
                if  'disk2d' in obj['type'].lower():
                    #test_time = time.time()
                    pintflux=0.0
                    if  'pintflux' in obj:
                        pintflux=obj['pintflux']
                    imodel=model_disk2d(models['header@'+image],obj['xypos'][0],obj['xypos'][1],
                                             r_eff=obj['sbser'][0],n=obj['sbser'][1],posang=obj['pa'],
                                             ellip=1.-np.cos(np.deg2rad(obj['inc'])),
                                             pintflux=pintflux,
                                             intflux=obj['intflux'],restfreq=obj['restfreq'],alpha=obj['alpha'])
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('test:'+image,time.time() - test_time))
                    #print(imodel.shape)
                    models['imod2d@'+image]+=imodel
                    models['imodel@'+image]+=imodel
                    
    
                if  'disk3d' in obj['type'].lower():
                    #test_time = time.time()              
                    
                    imodel,imodel_prof=model_disk3d(models['header@'+image],obj,nsamps=nsamps,fixseed=False,mod_dct=mod_dct)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('test:'+image,time.time() - test_time))
                    #print(imodel.shape)
                    models['imod3d@'+image]+=imodel
                    models['imod3d_prof@'+tag+'@'+image]=imodel_prof.copy()
                    models['imodel@'+image]+=imodel              
                    
    if  verbose==True:            
        print(">>>>>{0:^10} : {1:<8.5f} seconds ---\n".format('fill-total',time.time() - start_time))
    
    return

#@profile
def model_simobs(models,decomp=False,verbose=False):
    """
    Simulate observations (dataset by dataset)
    
    models is expected to be a mutable dict reference, and we don't really create any new objects
    
    Notes (on evaluating efficiency):
    
        While building the intrinsic data-model from a physical model can be expensive,
        the simulated observation (i.e. 2D/3D convol or UV sampling) is usually the bottle-neck.
        
        To improve the performance, we implement some optimizations:
            for imaging-domain simulation:
                + merge all components (e.g.overlapping objects, lines) in the intrinsic/reference model before simulations, e.g.
                + exclude empty (masked/flux=0) regions
            for spectral-domain simulation:
                + seperate 2D component (continuum) from 3D component (line) and do simulation independently,
                  so only channels with the same emission morphology are process in a single simulation.
                  this is epsecially important if line emission only occapy a small number of channels
            
        
    print(uvmodel.flags)
    print(models[tag.replace('imod2d@','uvmodel@')].flags)                                      
    print(uvmodel is models[tag.replace('imod2d@','uvmodel@')])             
    
    the performance of model_uvsample is not very sensitive to the input image size.
    
    just make sure imodel match header; phasecenter offset will be take care of in model_uvsample
    
    """
    
    if  verbose==True:
        start_time = time.time()    
              
    for tag in list(models.keys()):
        
        if  'imod3d@' in tag:
            
            if  models[tag.replace('imod3d@','type@')]=='vis':
                #print('\n',tag.replace('imod3d@',''),' image model shape: ',models[tag].shape)
                if  decomp==True:
                    uvmodel=model_uvsample(models[tag]*models[tag.replace('imod3d@','pbeam@')],None,
                                                models[tag.replace('imod3d@','header@')],
                                                models[tag.replace('imod3d@','uvw@')],
                                                models[tag.replace('imod3d@','phasecenter@')],
                                                uvdtype=models[tag.replace('imod3d@','data@')].dtype,
                                                average=True,
                                                verbose=verbose)
                    models[tag.replace('imod3d@','uvmod3d@')]=uvmodel.copy() 
                    models[tag.replace('imod3d@','uvmodel@')]+=uvmodel.copy()
                    uvmodel=model_uvsample(None,models[tag.replace('imod3d@','imod2d@')]*models[tag.replace('imod3d@','pbeam@')],
                                            models[tag.replace('imod3d@','header@')],
                                            models[tag.replace('imod3d@','uvw@')],
                                            models[tag.replace('imod3d@','phasecenter@')],
                                            uvdtype=models[tag.replace('imod3d@','data@')].dtype,
                                            average=True,
                                            verbose=verbose)
                    models[tag.replace('imod3d@','uvmod2d@')]=uvmodel.copy() 
                    models[tag.replace('imod3d@','uvmodel@')]+=uvmodel.copy()                                          
                else:
                    if  np.sum(models[tag])==0.0:
                        xymod3d=None
                    else:
                        xymod3d=models[tag]*models[tag.replace('imod3d@','pbeam@')]
                    if  np.sum(models[tag.replace('imod3d@','imod2d@')]*models[tag.replace('imod3d@','pbeam@')])==0.0:
                        xymod2d=None
                    else:
                        xymod2d=models[tag.replace('imod3d@','imod2d@')]*models[tag.replace('imod3d@','pbeam@')]
                    uvmodel=model_uvsample(xymod3d,
                                           xymod2d,
                                           models[tag.replace('imod3d@','header@')],
                                           models[tag.replace('imod3d@','uvw@')],
                                           models[tag.replace('imod3d@','phasecenter@')],
                                           uvmodel=models[tag.replace('imod3d@','uvmodel@')],
                                           uvdtype=models[tag.replace('imod3d@','data@')].dtype,
                                           average=True,
                                           verbose=verbose)
                    #print('-->',uvmodel)                                   
            if  models[tag.replace('imod3d@','type@')]=='image':
                cmodel,kernel=model_convol(models[tag],
                                     models[tag.replace('imod3d@','header@')],
                                     psf=models[tag.replace('imod3d@','psf@')],
                                     returnkernel=True,
                                     average=False,
                                     verbose=verbose)
                models[tag.replace('imod3d@','cmod3d@')]=cmodel.copy()
                models[tag.replace('imod3d@','cmodel@')]+=cmodel.copy()
                models[tag.replace('imod3d@','kernel@')]=kernel.copy()
                cmodel,kernel=model_convol(models[tag.replace('imod3d@','imod2d@')],
                                     models[tag.replace('imod2d@','header@')],
                                     psf=models[tag.replace('imod2d@','psf@')],
                                     returnkernel=True,
                                     average=True,
                                     verbose=verbose)              
                models[tag.replace('imod3d@','cmod2d@')]=cmodel.copy()
                models[tag.replace('imod3d@','cmodel@')]+=cmodel.copy()
                models[tag.replace('imod3d@','kernel@')]=kernel.copy()                   
                              
        
    if  verbose==True:            
        print(">>>>>{0:^10} : {1:<8.5f} seconds ---".format('simulate-total',time.time() - start_time))
        
    return


def model_fill2(models,nsamps=100000,decomp=False,verbose=False):
    """
    create reference/intrinsic models and fill them into the model container

    Notes (on evaluating efficiency):
    
        While building the intrinsic data-model from a physical model can be expensive,
        the simulated observation (2D/3D convolution or UV sampling) is usually the bottle-neck.
        
        some tips to improve the effeciency:
            + exclude empty (masked/flux=0) region for the convolution
            + joint all objects in the intrinsic model before the convolution, e.g.
                overlapping objects, lines
            + use to low-dimension convolution when possible (e.g. for the narrow-band continumm) 
            
        before splitting line & cont models:
            --- apicall   : 2.10178  seconds ---
        after splitting line & cont models:
            --- apicall   : 0.84662  seconds ---
    
    
    """
    
    if  verbose==True:
        start_time = time.time()    

    mod_dct=models['mod_dct']
    
    #   add ref models OBJECT by OBJECT
                
    for tag in list(mod_dct.keys()):

        #   skip if no "type" or the item is not a physical model
        
        obj=mod_dct[tag]
        
        if  verbose==True:
            print("+"*40); print('@',tag); print('type:',obj['type']) ; print("-"*40)

        if  'vis' in mod_dct[tag].keys():
            
            vis_list=mod_dct[tag]['vis'].split(",")
            
            for vis in vis_list:
                
                test_time = time.time()
                
                if  'disk2d' in obj['type'].lower():
                    #test_time = time.time()

                    model_disk2d2(models['header@'+vis],obj,
                                        model=models['imodel@'+vis],
                                        factor=5)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('fill:  '+tag+'-->'+vis+' disk2d',time.time() - test_time))
                    #print(imodel.shape)
                    #models['imod2d@'+vis]+=imodel
                    #models['imodel@'+vis]+=imodel
                    
                if  'disk3d' in obj['type'].lower():
                    #pprint(obj)
                    #test_time = time.time()              
                    imodel_prof=model_disk3d2(models['header@'+vis],obj,
                                                    model=models['imodel@'+vis],
                                                    nsamps=nsamps,fixseed=False,mod_dct=mod_dct)
                    #print("---{0:^10} : {1:<8.5f} seconds ---".format('fill:  '+tag+'-->'+vis+' disk3d',time.time() - test_time))
                    #print(imodel.shape)
                    #models['imod3d@'+vis]+=imodel
                    models['imod3d_prof@'+tag+'@'+vis]=imodel_prof.copy()
                    #models['imodel@'+vis]+=imodel     
                    
          
                    
    if  verbose==True:            
        print(">>>>>{0:^10} : {1:<8.5f} seconds ---\n".format('fill-total',time.time() - start_time))
    
    return