"""
generate mockup data
"""


import numpy as np
from astropy.io import fits 
import gmake
from gmake.utils import pprint
import astropy.units as u
from astropy.wcs import WCS

gmake.logger_config(logfile='gmake.log',loglevel='DEBUG',logfilelevel='DEBUG')
from rxutils.casa.imager import invert 
from rxutils.casa.proc import setLogfile
from astropy.cosmology import Planck13
import astropy.units as u
from copy import deepcopy

def create_mockup_xy(inpname='mockup_baisc.inp'):

    inpfile=gmake.__demo__+'/../gmake/tests/data/'+inpname
    inp_dct=gmake.read_inp(inpfile)
    version=inpname.replace('.inp','')
    
    # generate cloudlets model 
    mod_dct=gmake.inp2mod(inp_dct)
    gmake.clouds_fill(mod_dct,nc=1000000,nv=30)
    
    # we didn't setup model container and initizlie essential metadata (e.g. PSF, error map)
    # we directly call xy_mapper here so no need to go throught models->model_mapper()
    # models=gmake.model_setup(mod_dct,dat_dct)
    
    header=gmake.meta.create_header()
    
    header['NAXIS3']=128
    header['NAXIS2']=256
    header['NAXIS1']=256
    
    header['CRVAL1']=189.2995416666666 
    header['CDELT1']=-0.03/3600
    header['CRPIX1']=128
    
    header['CRVAL2']=62.36994444444444
    header['CDELT2']=0.03/3600 
    header['CRPIX2']=128
    
    header['CRVAL3']=45535299115.90349
    header['CDELT3']=2000013.13785553
    header['CRPIX3']=1.0   
    
    beam=(0.5*u.arcsec,0.3*u.arcsec,20*u.deg)
    psf=gmake.makepsf(header,beam=beam,norm='peak')
     
    cube,scube=gmake.xy_mapper([mod_dct['co21']],WCS(header),psf=psf)
    
    header['BUNIT']='Jy/pixel'
    del header['BPA']
    del header['BMIN']
    del header['BMAJ']
    fits.writeto(version+'.fits',cube,header,overwrite=True)
    
    header['BUNIT']='Jy/beam'
    header['BMAJ']=beam[0].to_value(u.deg)
    header['BMIN']=beam[1].to_value(u.deg)
    header['BPA']=beam[2].to_value(u.deg)
    fits.writeto(version+'_sm.fits',scube,header,overwrite=True)
    fits.writeto(version+'_psf.fits',psf,header,overwrite=True)
    
    sigma=2e-4
    dn=scube.shape
    scube+=np.random.randn(dn[0],dn[1],dn[2])*sigma
    fits.writeto(version+'_sn.fits',scube,header,overwrite=True)
    
    #   scale the noise level by 0.5 to mimick an underestimation of error
    fits.writeto(version+'_err.fits',\
                 np.broadcast_to(sigma*0.5,(dn[0],dn[1],dn[2])).astype(np.float32),\
                 header,overwrite=True)
    
    return

def create_mockup_uv(inpname='mockup_baisc.inp'):
    """
    https://casaguides.nrao.edu/index.php/Simulating_Observations_in_CASA_5.4
    """

    inpfile=gmake.__demo__+'/../gmake/tests/data/'+inpname
    inp_dct=gmake.read_inp(inpfile)
    version=inpname.replace('.inp','')
    #pprint(inp_dct)
    z=inp_dct['basics']['z']
    kps=Planck13.kpc_proper_per_arcmin(z).to(u.kpc/u.arcsec)
    r_beam=1.8*u.arcsec*kps
    reff_list=np.array([0.25,0.75,1.25])*r_beam
    # [ 3.20225876,  9.60677627, 16.01129378] kpc
    sigm_list=np.array([0.05,0.1,0.5])#in Jy

    
    #"""
    # load the uvw/chanfreq framework 
    #dat_dct=gmake.read_data(inp_dct)    
    
    msname='../../../examples/data/gn20/vla/AC974.110428.ms'
    msname='../../../examples/data/gn20/vla/AC974.100409.ms'
    dat_dct=gmake.read_ms(vis=msname)
    
    for i in range(3):
        for j in range(3):
    
            mod_dct=gmake.inp2mod(inp_dct)
            if  j==0: 
                continue
            
            
            gmake.utils.write_par(mod_dct,'sbProf[1]@co21',reff_list[i])
            simplenoise=str(sigm_list[j])+'Jy'
            version1=version+'_'+str(i)+str(j)
            pprint(mod_dct)

            
            # generate cloudlets model 
            gmake.clouds_fill(mod_dct,nc=1000000,nv=30)
            
            #   get a "pesodo" header
            
            obj=mod_dct['co21']
            #center=[obj['xypos'].ra,obj['xypos'].dec]
            center=dat_dct['phasecenter@'+msname]
            header=gmake.makeheader(dat_dct['uvw@'+msname],
                                    center,
                                    dat_dct['chanfreq@'+msname],
                                    dat_dct['chanwidth@'+msname],
                                    antsize=25*u.m)
            #   get uvmodel data
            
            w=WCS(header)    
            uvmodel=gmake.uv_mapper([mod_dct['co21']],w,
                                    dat_dct['data@'+msname],
                                    dat_dct['uvw@'+msname],
                                    dat_dct['phasecenter@'+msname],
                                    dat_dct['weight@'+msname],
                                    dat_dct['flag@'+msname])
            #   write out model MS
            
            gmake.write_ms(version1+'.ms',uvmodel,datacolumn='data',inputvis=msname) 
            gmake.corrupt_ms(version1+'_withnoise.ms',inputvis=version1+'.ms',
                             mode='simplenoise',simplenoise=simplenoise)
            
            #   write intrinsic model
            cube=gmake.xy_mapper([mod_dct['co21']],WCS(header))
            header['BUNIT']='Jy/pixel'
            del header['BPA']
            del header['BMIN']
            del header['BMAJ']
            fits.writeto(version1+'.ms/im.fits',cube,header,overwrite=True)
            
            #   write PB model
            pb=gmake.makepb(header,phasecenter=dat_dct['phasecenter@'+msname],antsize=12*u.m)
            fits.writeto(version1+'.ms/im_pb.fits',pb,header,overwrite=True)    
                              
            #   do invert  
            setLogfile('casa.log')
            invert(version1+'.ms',version1+'.ms/dm',cell=0.25,imsize=[256,256],datacolumn='data',start=0,nchan=120,width=1,onlydm=False)
            invert(version1+'_withnoise.ms',version1+'_withnoise.ms/dm',cell=0.25,imsize=[256,256],datacolumn='data',start=0,nchan=120,width=1,onlydm=False)    
    
    return

    
if  __name__=="__main__":
    
    #cd ~Resilio/Workspace/projects/GMaKE/gmake/tests/data/
    
    #create_mockup_xy('mockup_basic.inp')
    #create_mockup_xy('mockup_spiral2.inp')     
    
    create_mockup_uv('mockup_basic.inp')
    #invert_mockup_uv('mockup_basic')
    #create_mockup_uv('mockup_spiral2.inp')      