from .model_func import *
from .model_build import *
from .model_dynamics import model_vrot
from .io import *

logger = logging.getLogger(__name__)

import builtins
import gc


import os
import psutil
process = psutil.Process(os.getpid())

#from .meta import dat_dct_global

import gmake.meta as meta

from memory_profiler import profile



def model_lnlike(theta,fit_dct,inp_dct,dat_dct,
                 savemodel=None,decomp=False,nsamps=1e5,
                 returnwdev=False,
                 verbose=False,test_threading=False):
    """
    the likelihood function
    
        step:    + fill the varying parameter into inp_dct
                 + convert inp_dct to mod_dct
                 + use mod_dct to regenerate RC
    """
    
    blobs={'lnprob':0.0,
           'chisq':0.0,
           'ndata':0.0,
           'wdev':np.array([]),
           'npar':len(theta)}
    if  returnwdev==False:
        del blobs['wdev']

        
    if  test_threading==True:
        #   don't actually calculate model
        #   used for testing threading overheads.
        x=dat_dct
        t = time.time() + np.random.uniform(0.01, 0.02)
        while True:
            if time.time() >= t:
                break
        return -np.inf,blobs
    
    inp_dct0=deepcopy(inp_dct)
    for ind in range(len(fit_dct['p_name'])):
        #print(fit_dct['p_name'][ind],theta[ind],fit_dct['p_unit'][ind],type(fit_dct['p_unit'][ind]))
        write_par(inp_dct0,fit_dct['p_name'][ind],theta[ind]*fit_dct['p_unit'][ind],verbose=False)
    
    #tic0=time.time()
    mod_dct=inp2mod(inp_dct0)   # in physical units
    model_vrot(mod_dct)         # in natural (default internal units)
    #print('Took {0} second on inp2mod'.format(float(time.time()-tic0))) 
    
    #tic0=time.time()
    #models=gmake_kinmspy_api(mod_dct,dat_dct=dat_dct)

    #if  savemodel is not None:
    #    nsamps=nsamps*10


    models=model_api(mod_dct,dat_dct,
                     decomp=decomp,nsamps=nsamps,verbose=verbose)
    #print('Took {0} second on one API call'.format(float(time.time()-tic0))) 
    #gmake_listpars(mod_dct)
    
    models_size=human_unit(get_obj_size(models)*u.byte)
    #logger.info("--- models size {:0.2f} ---".format(models_size))  
    


    #tic0=time.time()
    
    for key in models.keys(): 
        
        if  'data@' not in key:
            continue


        if  models[key.replace('data@','type@')]=='vis':
            
            
            start_time = time.time() #!!!!
            
            
            uvmodel=models[key.replace('data@','uvmodel@')]
            uvdata=models[key]
            
            
            """
            
            #size=human_unit(get_obj_size(models[key.replace('data@','imod3d@')])*u.byte)
            #size=human_to_string(size,format_string='{0:3.0f} {1}')
            #print(size,(models[key.replace('data@','imod3d@')]).shape)            
            
            #
            # averaging different correllation assumed to be RR/LL or XX/YY
            # don't use weight_spectrum here
            #        
            #uvdata=np.mean(models[key],axis=-1)                            # nrecord x nchan
            #weight=np.sum(models[key.replace('data@','weight@')],axis=-1)   # nrecord
            #weight=models[key.replace('data@','weight@')]
            #weight+spectrum=np.broadcast_to(weight[:,np.newaxis],uvmodel.shape)      # nrecord x nchan (just view for memory saving)
    
            nchan=(uvmodel.shape)[-1]
    
            weight_sqrt=ne.evaluate("sqrt(a)",
                               local_dict={"a":models[key.replace('data@','weight@')]})
            
            #weight_sqrt=np.sqrt(models[key.replace('data@','weight@')])        
            wdev=ne.evaluate("abs(a-b).real*c",
                             local_dict={'a':models[key],
                                         'b':models[key.replace('data@','uvmodel@')],
                                         'c':np.broadcast_to(weight_sqrt[:,np.newaxis],uvmodel.shape)})

            
            
            #wdev=ne.evaluate("abs(a-b).real*sqrt(c)",
            #                 local_dict={'a':models[key],
            #                             'b':models[key.replace('data@','uvmodel@')],
            #                             'c':np.broadcast_to((models[key.replace('data@','weight@')])[:,np.newaxis],uvmodel.shape)})
            
            lnl1=ne.evaluate("sum(wdev**2)")    # speed up for long vectors:  lnl1=np.sum( wdev**2 )
                                                # lnl1=ne.evaluate("sum((where(wdev==wdev, wdev,0))**2)")
            lnl2=ne.evaluate("sum(-log(a))",
                             local_dict={'a':models[key.replace('data@','weight@')]})*nchan + \
                 np.log(2.0*np.pi)*uvdata.size
            
            lnl=-0.5*(lnl1+lnl2)        
            blobs['lnprob']+=lnl
            blobs['chisq']+=lnl1
            blobs['ndata']+=wdev.size
            

            #logger.debug("{0} {1} {2}".format(key,lnl1,wdev.size))
            
            if  returnwdev==True:
                blobs['wdev']=np.append(blobs['wdev'],wdev)
            
            
            """
            chi2=ne.evaluate('sum( ((a.real-b.real)**2.0+(a.imag-b.imag)**2)*(~f*c) )',
                             local_dict={'a':models[key],
                                         'b':models[key.replace('data@','uvmodel@')],
                                         'f':models[key.replace('data@','flag@')],
                                         'c':(models[key.replace('data@','weight@')])[:,np.newaxis]})
            blobs['chisq']+=chi2
            blobs['ndata']+=np.sum(~models[key.replace('data@','flag@')])
            #logger.debug("{0} {1}".format(key,chi2))
            
            #logger.debug("{0:50} : {1:<8.5f} seconds".format('one trial',time.time()-start_time)) #!!!!
            
        #print("---{0:^30} : {1:<8.5f} seconds ---\n".format('chisq',time.time() - tic0))

        if  models[key.replace('data@','type@')]=='image':
            
            im=models[key]
            hd=models[key.replace('data@','header@')]        
            mo=models[key.replace('data@','cmodel@')]
            em=models[key.replace('data@','error@')]
            mk=models[key.replace('data@','mask@')]
            sp=models[key.replace('data@','sample@')]
            
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
    
            if  sp is not None:
                imtmp=np.squeeze(em)
                nxyz=np.shape(imtmp)
                if  len(nxyz)==3:
                    imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1]),np.arange(nxyz[2])),\
                                                imtmp,sp[:,::-1],method='linear')
                else:
                    imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1])),\
                                                imtmp,sp[:,1::-1],method='linear')
                sigma2=imtmp**2.
                imtmp=np.squeeze(im-mo)
                
                if  len(nxyz)==3:
                    imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1]),np.arange(nxyz[2])),\
                                                imtmp,sp[:,::-1],method='linear')
                else:
                    imtmp=interpn((np.arange(nxyz[0]),np.arange(nxyz[1])),\
                                                imtmp,sp[:,1::-1],method='linear')
            else:
                
                sigma2=np.ravel(np.squeeze(em)**2.)
                imtmp=np.ravel(np.squeeze(im-mo))
                mk=np.ravel(mk)
                sigma2=sigma2[np.where(mk==0)]
                imtmp=imtmp[np.where(mk==0)]
            
            #print(sp[:,1::-1])
    
            lnl1=np.nansum( (imtmp)**2/sigma2 )
            lnl2=np.nansum( np.log(sigma2*2.0*np.pi) )
            lnl=-0.5*(lnl1+lnl2)
            wdev=imtmp/np.sqrt(sigma2)
      
            
            blobs['lnprob']+=lnl
            blobs['chisq']+=lnl1
            
            blobs['ndata']+=wdev.size

            if  returnwdev==True:
                blobs['wdev']=np.append(blobs['wdev'],wdev)         


    if  savemodel is not None:
        #   remove certain words from long file names 

        outname_exclude=None
        if  'shortname' in inp_dct['general'].keys():
            outname_exclude=inp_dct['general']['shortname']
        if  'outname_exclude' in inp_dct['general'].keys():
            outname_exclude=inp_dct['general']['outname_exclude']
            
        outname_replace=None
        if  'outname_replace' in inp_dct['general'].keys():
            outname_replace=inp_dct['general']['outname_replace']
                                
        #print(savemodel)
        #print(outname_exclude)
        #print(outname_replace)
        export_model(models,outdir=savemodel,
                     outname_exclude=outname_exclude,
                     outname_replace=outname_replace)
        
        models_keys=list(models.keys())
        data_keys=list(dat_dct.keys())
        for key in models_keys:
            if  key in data_keys:
                del models[key]
        dct2hdf(models,savemodel+'/'+'models.h5')
        
        #pprint(inp_dct0)
        write_inp(inp_dct0,inpfile=savemodel+'/model.inp',overwrite=True)             
    
    print(get_obj_size(models,to_string=True))
    #
    models=None

    lnl=blobs['lnprob']
    logger.debug("{0} {1}".format('-->',blobs['chisq']))
    
    return lnl,blobs

#@profile

def model_lnprior(theta,fit_dct):
    """
    pass through the likelihood prior function (limiting the parameter space)
    """
    p_lo=fit_dct['p_lo']
    p_up=fit_dct['p_up']
    for index in range(len(theta)):
        if  theta[index]<p_lo[index] or theta[index]>p_up[index]:
            return -np.inf
    return 0.0


def model_lnprob(theta,fit_dct,inp_dct,dat_dct,
                 savemodel=None,decomp=False,nsamps=1e5,
                 packblobs=False,
                 verbose=False):
    """
    this is the evaluating function for emcee
    packblobs=True:
        lnl,blobs
    packblobs=False:
        lnl,lnp,chisq,ndata,npar
    """

    if  verbose==True:
        start_time = time.time()
        
    lp = model_lnprior(theta,fit_dct)
    
    if  not np.isfinite(lp):
        blobs={'lnprob':-np.inf,'chisq':+np.inf,'ndata':0.0,'npar':len(theta)}
        if  packblobs==True:
            return -np.inf,blobs
        else:
            return -np.inf,-np.inf,+np.inf,0.0,len(theta)

     
             
    lnl,blobs=model_lnlike(theta,fit_dct,inp_dct,dat_dct,
                           savemodel=savemodel,decomp=decomp,nsamps=nsamps,
                           verbose=verbose)
    
    if  verbose==True:
        print("try ->",theta)
        print("---{0:^10} : {1:<8.5f} seconds ---".format('lnprob',time.time()-start_time))    
    
    # np.array: to creat a zero-d object array 
    if  packblobs==True:
        return lp+lnl,blobs
    else:
        return lp+lnl,blobs['lnprob'],blobs['chisq'],blobs['ndata'],blobs['npar']

    
    
def model_lnprob_global(theta,fit_dct,inp_dct,
                 savemodel=None,decomp=False,nsamps=1e5,
                 packblobs=False,
                 verbose=False):
    """
    this is the evaluating function for emcee
    packblobs=True:
        lnl,blobs
    packblobs=False:
        lnl,lnp,chisq,ndata,npar
    """

    if  verbose==True:
        start_time = time.time()
        
    lp = model_lnprior(theta,fit_dct)
    if  not np.isfinite(lp):
        blobs={'lnprob':-np.inf,'chisq':+np.inf,'ndata':0.0,'npar':len(theta)}
        if  packblobs==True:
            return -np.inf,blobs
        else:
            return -np.inf,-np.inf,+np.inf,0.0,len(theta)
    
    lnl,blobs=model_lnlike(theta,fit_dct,inp_dct,meta.dat_dct_global,
                           savemodel=savemodel,decomp=decomp,nsamps=nsamps,
                           verbose=verbose)
    if  verbose==True:
        print("try ->",theta)
        print("---{0:^10} : {1:<8.5f} seconds ---".format('lnprob',time.time()-start_time))    
    
    # np.array: to creat a zero-d object array 
    if  packblobs==True:
        return lp+lnl,blobs
    else:
        return lp+lnl,blobs['lnprob'],blobs['chisq'],blobs['ndata'],blobs['npar']    


def model_chisq(theta,
                      fit_dct=None,inp_dct=None,dat_dct=None,
                      savemodel=None,
                      verbose=False):
    """
    this is the evaluating function for amoeba 
    """
    #print(theta)
    if  verbose==True:
        start_time = time.time()
        
    lp = model_lnprior(theta,fit_dct)
    if  lp!=0:
        lp=+np.inf
    if  not np.isfinite(lp):
        blobs={'lnprob':-np.inf,'chisq':+np.inf,'ndata':0.0,'npar':len(theta)}
        #return +np.inf,blobs
        return +np.inf
    
    lnl,blobs=model_lnlike(theta,fit_dct,inp_dct,dat_dct,savemodel=savemodel)
    
    if  verbose==True:
        print("try ->",theta)
        print("---{0:^10} : {1:<8.5f} seconds ---".format('lnprob',time.time()-start_time))    
    
    #print('-->',lp+blobs['chisq'])
    return lp+blobs['chisq']       




def model_lmfit_wdev(params,
                     #fjac=None, x=None, y=None, err=None,
                     fit_dct=None,inp_dct=None,dat_dct=None,
                     blobs=None,      # save the metadata along / list
                     savemodel=None,
                     verbose=True):
    """
    this is the evaluating function for mpfit
    return weighted deviations:
        http://cars9.uchicago.edu/software/python/mpfit.html
        or
        from mgefit
    """
    theta=[]
    for key in params:
        theta.append(params[key].value)
    theta=np.array(theta)
    
    status=0
    if  verbose==True:
        start_time = time.time()
        
    lp = model_lnprior(theta,fit_dct)
    if  lp!=0:
        lp=+np.inf
#     if  not np.isfinite(lp):
#         blobs={'lnprob':-np.inf,'chisq':+np.inf,'ndata':0.0,'npar':len(theta)}
#         #return +np.inf,blobs
#         return +np.inf
    
    lnl,blob=model_lnlike(theta,fit_dct,inp_dct,dat_dct,savemodel=savemodel)
 
    wdev=blob['wdev'].flatten().copy()
    
    if  blobs is not None:
        blobs['pars'].append(theta)
        blobs['chi2'].append(blob['chisq'])

    if  verbose==True:
        print("")
        print('ifeva: ',len(blobs['chi2']))
        print('try:   ',theta)
        print('chisq: ','{0:>16.2f} {1:>16.2f}'.format(np.sum(wdev**2.0),wdev.size))
        print("---{0:^10} : {1:<8.5f} seconds ---".format('lnprob',time.time()-start_time))

    return wdev       


##############################################################################################

def model_lnlike2_old(theta,fit_dct,inp_dct,dat_dct,
                 savemodel=None,decomp=False,nsamps=1e5,
                 returnwdev=False,
                 verbose=False,test_threading=False):
    """
    the likelihood function
    
        step:    + fill the varying parameter into inp_dct
                 + convert inp_dct to mod_dct
                 + use mod_dct to regenerate RC
    """

    
    blobs={'lnprob':0.0,
           'chisq':0.0,
           'ndata':0.0,
           'wdev':np.array([]),
           'npar':len(theta)}
    if  returnwdev==False:
        del blobs['wdev']

    #models_size=human_unit(get_obj_size(fit_dct)*u.byte)
    #logger.info("before models size {:0.2f} ---".format(models_size))
    #models_size=human_unit(get_obj_size(inp_dct)*u.byte)
    #logger.info("before models size {:0.2f} ---".format(models_size))    
    

    
    """
    if  test_threading==True:
        #   don't actually calculate model
        #   used for testing threading overheads.
        x=dat_dct       
        t = time.time() + np.random.uniform(0.1, 0.2)
        while True:
            if time.time() >= t:
                break
        return 0.0,blobs
    """
    
    inp_dct0=deepcopy(inp_dct)

        
    for ind in range(len(fit_dct['p_name'])):
        #print(fit_dct['p_name'][ind],theta[ind],fit_dct['p_unit'][ind],type(fit_dct['p_unit'][ind]))
        write_par(inp_dct0,fit_dct['p_name'][ind],theta[ind]*fit_dct['p_unit'][ind],verbose=False)
    
 
        
    #tic0=time.time()
    mod_dct=inp2mod(inp_dct0)   # in physical units
    model_vrot(mod_dct)         # in natural (default internal units)
    #print('Took {0} second on inp2mod'.format(float(time.time()-tic0))) 


    if  test_threading==True:
        #   don't actually calculate model
        #   used for testing threading overheads.
        x=dat_dct       
        t = time.time() + np.random.uniform(1.1, 1.2)
        while True:
            if time.time() >= t:
                break
        return 0.0,blobs         
        
    
    #tic0=time.time()
    #models=gmake_kinmspy_api(mod_dct,dat_dct=dat_dct)

    #if  savemodel is not None:
    #    nsamps=nsamps*10

    #print('before',process.memory_info().rss/1024/1024)
    #logger.info("before models size {:0.2f} ---".format(models_size))    
     
    models=model_init2(mod_dct,dat_dct,decomp=decomp,verbose=verbose)
    models_size=human_unit(get_obj_size(models)*u.byte)

       
    model_fill2(models,decomp=decomp,nsamps=nsamps,verbose=verbose)
    #print(get_obj_size(models,to_string=True))
    #print('before',process.memory_info().rss/1024/1024)
      
    
    #models_size=human_unit(get_obj_size(models)*u.byte)
    #logger.info("--- models size {:0.2f} ---".format(models_size))      
    
    #models_size=human_unit(get_obj_size(models)*u.byte)
    #logger.info("before models size {:0.2f} ---".format(models_size))
    #for key in models:
    #    print(key,get_obj_size(models[key])/1024/1024)    
    


    
    
    #print(get_obj_size(models))
    #print(blobs['lnprob'])
    #models_size=human_unit(get_obj_size(models)*u.byte)
    #logger.info("after models size {:0.2f} ---".format(models_size))    
    

        
    
    #models_size=human_unit(get_obj_size(models)*u.byte)
    #logger.info("--- models size {:0.2f} ---".format(models_size))
    

    
        
    #for key in models:
    #    print(key,get_obj_size(models[key])/1024/1024)
        
    for tag in list(models.keys()):
        
        if  'imodel@' in tag:
            
            if  models[tag.replace('imodel@','type@')]=='vis':
                #print(models[tag])
                chi2=model_uvchi2(models[tag],#*models[tag.replace('imod3d@','pbeam@')],
                                     #models[tag.replace('imod3d@','imod2d@')],#*models[tag.replace('imod3d@','pbeam@')],
                                     models[tag.replace('imodel@','header@')],
                                     dat_dct[tag.replace('imodel@','data@')],
                                     dat_dct[tag.replace('imodel@','uvw@')],
                                     dat_dct[tag.replace('imodel@','phasecenter@')],
                                     dat_dct[tag.replace('imodel@','weight@')],
                                     dat_dct[tag.replace('imodel@','flag@')],
                                     average=True,
                                     verbose=verbose)
                #print(chi2)
                blobs['chisq']+=chi2
                blobs['ndata']+=np.sum(~dat_dct[tag.replace('imodel@','flag@')])
                #logger.debug("{0} {1}".format(tag,chi2))
    
    lnl=blobs['lnprob']
    #print('after',process.memory_info().rss/1024/1024)
    #logger.debug("{0} {1}".format('-->',blobs['chisq']))
    return lnl,blobs    

if  __name__=="__main__":
    
    pass


