from __future__ import print_function

import numpy as np
from astropy.modeling.models import Sersic2D
import matplotlib.pyplot as plt
from astropy.wcs import WCS
from astropy.io import fits
from astropy.convolution import convolve_fft
from astropy.convolution import convolve
from astropy.convolution import discretize_model
import pprint

#   FFT related
import scipy.fftpack 
import pyfftw #pyfftw3 doesn't work
import mkl_fft
#import reikna.fft

def gmake_model_api(mod_dct,dat_dct,
                      decomp=False,
                      verbose=False):
    """
    call for the model construction:
    
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
    """
    models={}
    
    #   FIRST PASS: add models OBJECT by OBJECT
    
    for tag in list(mod_dct.keys()):

        #   skip if no "method" or the item is not a physical model
        
        obj=mod_dct[tag]
        if  tag=='optimize':
            continue        
        if  'method' not in obj.keys():
            continue    
        if  verbose==True:
            print("+"*40); print('@',tag); print('method:',obj['method']) ; print("-"*40)

        image_list=mod_dct[tag]['image'].split(",")
        
        for image in image_list:
            
            if  'data@'+image not in models.keys():
                
                models['header@'+image]=dat_dct['header@'+image]
                models['data@'+image]=dat_dct['data@'+image]
                models['error@'+image]=dat_dct['error@'+image]   
                models['mask@'+image]=dat_dct['mask@'+image]
                models['sample@'+image]=dat_dct['sample@'+image]
                models['psf@'+image]=dat_dct['psf@'+image]
                models['imodel@'+image]=np.zeros_like(models['data@'+image])
                models['cmodel@'+image]=np.zeros_like(models['data@'+image])
                #   save 2d objects (even it has been broadcasted to 3D for spectral cube)
                models['imod2d@'+image]=np.zeros_like(models['data@'+image])
                #   save 3D objects (like spectral line emission from kinmspy/tirific)
                models['imod3d@'+image]=np.zeros_like(models['data@'+image])
  
                
            if  'disk2d' in obj['method'].lower():
                imodel=gmake_model_disk2d(models['header@'+image],obj['xypos'][0],obj['xypos'][1],
                                         r_eff=obj['sbser'][0],n=obj['sbser'][1],posang=obj['pa'],
                                         ellip=1.-np.cos(np.deg2rad(obj['inc'])),
                                         intflux=obj['intflux'],restfreq=obj['restfreq'],alpha=obj['alpha'])
                models['imod2d@'+image]+=imodel
                models['imodel@'+image]+=imodel

            if  'kinmspy' in obj['method'].lower():                
                imodel=gmake_model_kinmspy(models['header@'+image],obj)
                models['imod3d@'+image]+=imodel
                models['imodel@'+image]+=imodel                

    #   SECOND PASS (OPTIONAL): simulate observations IMAGE BY IMAGE
    
    #start_time = time.time()
    
    for tag in list(models.keys()):
        
        """
        if  'imodel@' in tag:
            print(tag)
            cmodel,kernel=gmake_model_simobs(models[tag],
                                             models[tag.replace('imodel@','header@')],
                                             psf=models[tag.replace('imodel@','psf@')],
                                             returnkernel=True,
                                             verbose=True)
            models[tag.replace('imodel@','cmodel@')]=cmodel.copy()
            models[tag.replace('imodel@','kernel@')]=kernel.copy()
        """
        
        #"""
        if  'imod2d@' in tag:
            #print(tag)
            cmodel,kernel=gmake_model_simobs(models[tag],
                                 models[tag.replace('imod2d@','header@')],
                                 psf=models[tag.replace('imod2d@','psf@')],
                                 returnkernel=True,
                                 average=True,
                                 verbose=False)
            #models[tag.replace('imod2d@','cmod2d@')]=cmodel.copy()
            models[tag.replace('imod2d@','cmodel@')]+=cmodel.copy()
            models[tag.replace('imod2d@','kernel@')]=kernel.copy()

        if  'imod3d@' in tag:
            #print(tag)
            cmodel,kernel=gmake_model_simobs(models[tag],
                                 models[tag.replace('imod3d@','header@')],
                                 psf=models[tag.replace('imod3d@','psf@')],
                                 returnkernel=True,
                                 average=False,
                                 verbose=False)
            #models[tag.replace('imod3d@','cmod3d@')]=cmodel.copy()
            models[tag.replace('imod3d@','cmodel@')]+=cmodel.copy()
            models[tag.replace('imod3d@','kernel@')]=kernel.copy()
        #"""
                        
    #print("---{0:^10} : {1:<8.5f} seconds ---".format('simobs',time.time()-start_time))
    
    return models                

def gmake_model_lnlike(theta,fit_dct,inp_dct,dat_dct,
                         savemodel='',
                         verbose=False):
    """
    the likelihood function
    """
    
    blobs={'lnprob':0.0,'chisq':0.0,'ndata':0.0,'npar':len(theta)}
     
    inp_dct0=deepcopy(inp_dct)
    for ind in range(len(fit_dct['p_name'])):
        #print("")
        #print('modify par: ',fit_dct['p_name'][ind],theta[ind])
        #print(gmake_readpar(inp_dct0,fit_dct['p_name'][ind]))
        gmake_writepar(inp_dct0,fit_dct['p_name'][ind],theta[ind])
        #print(">>>")
        #print(gmake_readpar(inp_dct0,fit_dct['p_name'][ind]))
        #print("")
    #gmake_listpars(inp_dct0)
    #tic0=time.time()
    mod_dct=gmake_inp2mod(inp_dct0)
    #print('Took {0} second on inp2mod'.format(float(time.time()-tic0))) 
    
    #tic0=time.time()
    #models=gmake_kinmspy_api(mod_dct,dat_dct=dat_dct)
    if  savemodel!='':
        cleanout=True
    else:
        cleanout=False
    models=gmake_model_api(mod_dct,dat_dct=dat_dct,
                           decomp=False,cleanout=cleanout,verbose=False)
    #print('Took {0} second on one API run'.format(float(time.time()-tic0))) 
    #gmake_listpars(mod_dct)
     
    
    for key in models.keys(): 
        
        if  'data@' not in key:
            continue
        
        im=models[key]
        hd=models[key.replace('data@','header@')]        
        mo=models[key.replace('data@','model@')]
        em=models[key.replace('data@','error@')]
        mk=models[key.replace('data@','mask@')]
        sp=models[key.replace('data@','sample@')]
        if  key.replace('data@','cmodel@') in models.keys():
            cm=models[key.replace('data@','cmodel@')]        
        if  key.replace('data@','psf@') in models.keys():
            pf=models[key.replace('data@','psf@')]
        
        #tic0=time.time()

        
        """
        sigma2=em**2
        #lnl1=np.sum( (im-mo)**2/sigma2*mk )
        #lnl2=np.sum( (np.log(sigma2)+np.log(2.0*np.pi))*mk )
        lnl1=np.sum( ((im-mo)**2/sigma2)[mk==1] )
        lnl2=np.sum( (np.log(sigma2)+np.log(2.0*np.pi))[mk==1] )
        lnl=-0.5*(lnl1+lnl2)
        blobs['lnprob']+=lnl
        blobs['chisq']+=lnl1
        blobs['ndata']+=np.sum(mk)
        """
        
        #print(im.shape)
        #print(sp.shape)
        #print(sp[:,2:0:-1].shape)
        #"""
        imtmp=np.squeeze(em)
        nxyz=np.shape(imtmp)
        if  len(nxyz)==3:
            imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1]),np.arange(nxyz[2])),\
                                        imtmp,sp[:,::-1],method='linear')
        else:
            imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1])),\
                                        imtmp,sp[:,1::-1],method='linear')
        sigma2=imtmp**2.0
        imtmp=np.squeeze(im-mo)
        
        if  len(nxyz)==3:
            imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1]),np.arange(nxyz[2])),\
                                        imtmp,sp[:,::-1],method='linear')
        else:
            imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1])),\
                                        imtmp,sp[:,1::-1],method='linear')
        
        #print(sp[:,1::-1])
        lnl1=np.sum( (imtmp)**2/sigma2 )
        lnl2=np.sum( np.log(sigma2*2.0*np.pi) )
        lnl=-0.5*(lnl1+lnl2)
        
        blobs['lnprob']+=lnl
        blobs['chisq']+=lnl1
        blobs['ndata']+=(np.shape(sp))[0]
        
        if  savemodel!='':
            basename=key.replace('data@','')
            basename=os.path.basename(basename)
            if  not os.path.exists(savemodel):
                os.makedirs(savemodel)
            fits.writeto(savemodel+'/data_'+basename,im,hd,overwrite=True)
            fits.writeto(savemodel+'/model_'+basename,mo,hd,overwrite=True)
            fits.writeto(savemodel+'/error_'+basename,em,hd,overwrite=True)
            fits.writeto(savemodel+'/mask_'+basename,mk,hd,overwrite=True)
            fits.writeto(savemodel+'/residual_'+basename,im-mo,hd,overwrite=True)
            if  key.replace('data@','cmodel@') in models.keys():
                fits.writeto(savemodel+'/cmodel_'+basename,cm,hd,overwrite=True)            
            if  key.replace('data@','psf@') in models.keys():
                fits.writeto(savemodel+'/psf_'+basename,pf,hd,overwrite=True)
        #"""
        #print('Took {0} second on calculating lnl/blobs'.format(float(time.time()-tic0)),key)
    lnl=blobs['lnprob']
    
    return lnl,blobs


def gmake_model_export(models,outdir='./'):
    """
        export model into FITS
    """
    for key in models.keys(): 
        
        if  'data@' not in key:
            continue
        
        basename=key.replace('data@','')
        basename=os.path.basename(basename)
        if  not os.path.exists(outdir):
            os.makedirs(outdir)
        versions=['data','imodel','cmodel','error','mask','kernel','psf','residual','imod2d','imod3d']
        hd=models[key.replace('data@','header@')]
        for version in versions:
            if  version=='residual' and key.replace('data@','cmodel@') in models.keys():
                fits.writeto(outdir+'/'+version+'_'+basename,
                             models[key]-models[key.replace('data@','cmodel@')],
                             models[key.replace('data@','header@')],
                             overwrite=True)                
            if  key.replace('data@',version+'@') in models.keys():
                fits.writeto(outdir+'/'+version+'_'+basename,
                             models[key.replace('data@',version+'@')],
                             models[key.replace('data@','header@')],
                             overwrite=True)


def gmake_model_lnprior(theta,fit_dct):
    """
    pass through the likelihood prior function (limiting the parameter space)
    """
    p_lo=fit_dct['p_lo']
    p_up=fit_dct['p_up']
    for index in range(len(theta)):
        if  theta[index]<p_lo[index] or theta[index]>p_up[index]:
            return -np.inf
    return 0.0

    
def gmake_model_lnprob(theta,fit_dct,inp_dct,dat_dct,
                         savemodel='',
                         verbose=False):
    """
    this is the evaluating function for emcee 
    """
    lp = gmake_model_lnprior(theta,fit_dct)
    if  not np.isfinite(lp):
        blobs={'lnprob':-np.inf,'chisq':+np.inf,'ndata':0.0,'npar':len(theta)}
        return -np.inf,blobs
    if  verbose==True:
        print("try ->",theta)
    lnl,blobs=gmake_model_lnlike(theta,fit_dct,inp_dct,dat_dct,savemodel=savemodel)
    return lp+lnl,blobs        


if  __name__=="__main__":
    
    pass


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


