from .utils import *
from .model_func_kinms import *

from galario.single import sampleImage

from io import StringIO
from asteval import Interpreter
import astropy.units as u
from astropy.coordinates import Angle
from astropy.coordinates import SkyCoord
aeval = Interpreter(err_writer=StringIO())
aeval.symtable['u']=u
aeval.symtable['SkyCoord']=SkyCoord

from sys import getsizeof
from .utils import human_unit
from .utils import human_to_string

import scipy.constants as const
from astropy.modeling.models import Gaussian2D
from astropy.modeling.models import Sersic1D
from astropy.modeling.models import Sersic2D
from astropy.convolution import discretize_model
from astropy.wcs import WCS

from copy import deepcopy

from scipy.interpolate import interp1d

from astropy.wcs.utils import proj_plane_pixel_area, proj_plane_pixel_scales
import numexpr as ne
import fast_histogram
import time
#import gc

from memory_profiler import profile

def model_disk2d(header,objp,
                 model=None,
                 factor=5):
    """
    insert a continuum model (frequency-independent) into a 2D image or 3D cube
    
    header:    data header including WCS
    
    ra,dec:    object center ra/dec
    ellip:     1-b/a
    posang:    in the astronomical convention
    r_eff:     in arcsec
    n:         sersic index
    
    intflux:   Jy
    restfreq:  GHz
    alpha:     
    
    co-centeral point souce: pintflux=0.0
    
    the header is assumed to be ra-dec-freq-stokes

    note:
        since the convolution is the bottom-neck, a plane-by-plane processing should
        be avoided.
        avoid too many header->wcs / wcs-header calls
        1D use inverse transsforming
    
    return model in units of Jy/pix  
    
    """
    
    obj=obj_defunit(objp)
    
    #   translate to dimensionless numerical value in default units

    ra=obj['xypos'][0]
    dec=obj['xypos'][1]
    r_eff=obj['sbser'][0]
    n=obj['sbser'][1]
    posang=obj['pa']
    ellip=1.-np.cos(np.deg2rad(obj['inc']))
    pintflux=0.0
    if  'pcontflux' in obj:
        pintflux=obj['pcontflux']    
    intflux=obj['contflux']
    restfreq=obj['restfreq']
    alpha=3.0
    if  'alpha' in obj:
        alpha=obj['alpha']
    
    #   build objects
    #   use np.meshgrid and don't worry about transposing
    w=WCS(header)
    cell=np.mean(proj_plane_pixel_scales(w.celestial))*3600.0
    #px,py=skycoord_to_pixel(SkyCoord(ra,dec,unit="deg"),w,origin=0) # default to IRCS
    px,py,pz,ps=(w.wcs_world2pix(ra,dec,0,0,0))
    vz=np.arange(header['NAXIS3'])
    wz=(w.wcs_pix2world(0,0,vz,0,0))[2]

    #   get 2D disk model
    mod = Sersic2D(amplitude=1.0,r_eff=r_eff/cell,n=n,x_0=px,y_0=py,
               ellip=ellip,theta=np.deg2rad(posang+90.0))
    xs_hz=int(r_eff/cell*7.0)
    ys_hz=int(r_eff/cell*7.0)
    #   use discretize_model(mode='oversample') 
    #       discretize_model(mode='center') or model2d=mod(x,y) may lead worse precision
    
    #   x,y = np.meshgrid(np.arange(header['NAXIS1']), np.arange(header['NAXIS2']))
    #   model2d=mod(x,y)

    #   intflux at different planes / broadcasting to the data dimension
    intflux_z=(wz/1e9/restfreq)**alpha*intflux    
    
    #option 1
    
    px_o_int=round(px-xs_hz)
    py_o_int=round(py-ys_hz)
    model2d=discretize_model(mod,
                             (px_o_int,px_o_int+2*xs_hz+1),
                             (py_o_int,py_o_int+2*ys_hz+1),
                             mode='oversample',factor=factor)
    model2d/=model2d/model2d.sum()
    model2d=model2d[np.newaxis,np.newaxis,:,:]*intflux_z[np.newaxis,:,np.newaxis,np.newaxis]

    if  model is None:
        model_out=np.zeros((header['NAXIS4'],header['NAXIS3'],header['NAXIS2'],header['NAXIS1']))
        model_out=paste_array(model_out,model2d,(0,0,int(py_o_int),int(px_o_int)),method='replace')
    else:
        model_out=model
        model_out=paste_array(model_out,model2d,(0,0,int(py_o_int),int(px_o_int)),method='add')
    
    #print(model2d.shape,'-->',model_out.shape)

    
    """
    #option 2
    model2d=discretize_model(mod,
                            (0,header['NAXIS1']),
                            (0,header['NAXIS2']),
                            mode='oversample',factor=factor)
    model2d=model2d/model2d.sum() 
    model+=model2d[np.newaxis,np.newaxis,:,:]*intflux_z[np.newaxis,:,np.newaxis,np.newaxis]
    model_out=model
    """
    
    if  pintflux!=0.0:
        pintflux_z=(wz/1e9/restfreq)**alpha*pintflux 
        model_out[0,:,int(np.round(py)),int(np.round(px))]+=pintflux_z
    
    if  model is None:
        return model_out
    else:
        return 
    #return #model_out


def model_disk3d(header,objp,
                 model=None,
                 nsamps=100000,decomp=False,fixseed=False,
                 verbose=False,
                 mod_dct=None):
    """
    handle modeling parameters to kinmspy and generate the model cubes embeded into 
    a dictionary nest
    
    note:
        kinmspy can only construct a spectral cube in the ra-dec-vel space. We use kinmspy
        to construct a xyv cube with the size sufficient to cover the model object. Then 
        we insert it into the data using the WCS/dimension info. 
    """    

    #######################################################################
    #   WORLD ----      DATA        ----    MODEL
    #######################################################################
    #   ra    ----      xi_data     ----    xSize/2.+phasecen[0]/cell
    #   dec   ----      yi_data     ----    ySize/2.+phasecen[1]/cell
    #   vsys  ----      vi_data     ----    vSize/2.+voffset/dv
    #
    # collect the world coordinates of the disk center (ra,dec,freq/wave)
    # note: vsys is defined in the radio(freq)/optical(wave) convention, 
    #       within the rest frame set at obj['z']/
    #       the convention doesn't really matter, as long as vsys << c
    #######################################################################
    #   vector description of the z-axis (data in Hz or m/s; model in km/s)
    #   rfreq=obj['restfreq']/(1.0+obj['z'])            # GHz (obs-frame)
    #   fsys=(1.0-obj['vsys']/(const.c/1000.0))*rfreq   # line systematic frequency (obs-frame)
    #   follow the convention / units defined in WCS:
    #   https://arxiv.org/pdf/astro-ph/0207407.pdf
    #   http://dx.doi.org/10.1051/0004-6361/201015362
    #   https://www.atnf.csiro.au/people/mcalabre/WCS/wcslib/wcsunits_8h.html#a25ba0f0129e88c6e7c74d4562cf796cd
    
    
    
    obj=obj_defunit(objp)
    #pprint(obj)
    
    w=WCS(header)
    if  'Hz' in header['CUNIT3']:
        wz=obj['restfreq']*1e9/(1.0+obj['z'])*(1.-obj['vsys']*1e3/const.c)
        dv=-const.c*header['CDELT3']/(1.0e9*obj['restfreq']/(1.0+obj['z']))/1000.
    if  'angstrom' in header['CUNIT3']:
        wz=obj['restwave']*(1.0+obj['z'])*(1.+obj['vsys']*1e3/const.c)/1e10
        dv=const.c*header['CDELT3']/(obj['restwave']*(1.0+obj['z']))/1000.
    if  'm/s' in header['CUNIT3']:
        wz=obj['vsys']*1000.
        dv=header['CDELT3']/1000.        
    #   wz: in hz / m or m.s
    #   dv: km/s
    
    #   get 0-based pix-index
    if  w.naxis==4:
        px,py,pz,ps=w.wcs_world2pix(obj['xypos'][0],obj['xypos'][1],wz,1,0)
    if  w.naxis==3:
        px,py,pz=w.wcs_world2pix(obj['xypos'][0],obj['xypos'][1],wz,0)
    #print(wz)
    #print(">>>>>>",(0,px,py,pz))
    ####
    #   About KinMS:
    #       + cube needs to be transposed to match the fits.data dimension 
    #       + the WCS/FITSIO in KINMSPY is buggy/offseted: don't use it
    #       + turn off convolution in kinmspy
    #       + KinMS only works in the RA/DEC/VELO domain.
    #       + KinMS is not preicse for undersampling SBPROFILE/VROT (linear interp -> integral)
    #           - we feed an oversampling vector to kinMS here.
    ####
    
    #####################
    
    #   build an oversampled SB vector.
    
    #mod = Sersic1D(amplitude=1.0,r_eff=obj['sbser'][0],n=obj['sbser'][1])
    #sbprof=mod(sbrad)
    
    #print(sbrad)
    #print(np.array(obj['radi']))
    #velrad=obj['radi']
    #velprof=obj['vrot']
    #gassigma=np.array(obj['vdis'])
    
    #   only extend to this range in vrot/sbprof
    #   this is the fine radii vector fed to kinmspy

    nsamps=int(nsamps)
    if  fixseed==True:
        seeds=[100,101,102,103]
    else:
        seeds=np.random.randint(0,100,4)
        # seeds[0] -> rad
        # seeds[1] -> phi
        # seeds[2] -> z
        # seeds[3] -> v_sigma    
    
    if  obj['pmodel'] is None:
        inclouds,prof1d=model_disk3d_inclouds(obj,seeds,nSamps=nsamps)
        rad=np.arange(0.,obj['sbser'][0]*7.0,obj['sbser'][0]/25.0)
    else:
        inclouds,prof1d=model_disk3d_inclouds_pmodel(obj,seeds,nSamps=nsamps)
        rad=np.arange(0.,np.nanmax(np.sqrt(inclouds[:,0]**2+inclouds[:,1]**2))+obj['sbser'][0]/25.0,obj['sbser'][0]/25.0)
    
    ikind='cubic'  # bad for extraplate but okay for interplate 'linear'/'quadratic'

    if  isinstance(obj['vrot'], (list, np.ndarray)):
        if_vrot=interp1d(np.array(obj['vrad']),np.array(obj['vrot']),kind=ikind,bounds_error=False,fill_value=(obj['vrot'][0],obj['vrot'][-1]))
        velprof=if_vrot(rad)
    if  isinstance(obj['vrot'], tuple):
        if  obj['vrot'][0].lower()=='dynamics':
            velprof=model_dynamics(obj,mod_dct[obj['vrot'][1]],rad)
        elif  obj['vrot'][0].lower()=='arctan':
            velprof=obj['vrot'][1]*2.0/np.pi*np.arctan(rad/obj['vrot'][2])
        elif  obj['vrot'][0].lower()=='exp':
            velprof=obj['vrot'][1]*(1-np.exp(-rad/obj['vrot'][2]))
        elif  obj['vrot'][0].lower()=='tanh':
            velprof=obj['vrot'][1]*np.tanh(rad/obj['vrot'][2])
        else:
            for ind in range(1,len(obj['vrot'])):
                aeval.symtable["p"+str(ind)]=obj['vrot'][ind]
                aeval.symtable["vrad"]=rad
            velprof=aeval(obj['vrot'][0])
    
    if  isinstance(obj['vdis'], (list, tuple, np.ndarray)):
        if_vdis=interp1d(np.array(obj['vrad']),np.array(obj['vdis']),kind=ikind,bounds_error=False,fill_value=(obj['vdis'][0],obj['vdis'][-1]))
        gassigma=if_vdis(rad)
    else:
        gassigma=rad*0.0+obj['vdis']
        obj['vdis']=np.array(obj['vrad'])*0.0+obj['vdis']
        
        
        
    
    """
    #   same as above
    if_vrot=interpolate.UnivariateSpline(np.array(obj['radi']),np.array(obj['vrot']),s=1.0,ext=3)
    velprof=if_vrot(velrad)
    #   not good for RC
    if_vrot=interp1d(np.array(obj['radi']),np.array(obj['vrot']),kind=ikind,bounds_error=False,fill_value='extrapolate')
    if_vdis=interp1d(np.array(obj['radi']),np.array(obj['vdis']),kind=ikind,bounds_error=False,fill_value='extrapolate')
    velprof=if_vrot(velrad)
    gassigma=if_vdis(velrad)    
    """

    
    ####################
    
    xs=np.max(rad)*1.0*2.0
    ys=np.max(rad)*1.0*2.0
    vs=np.max(velprof*np.abs(np.sin(np.deg2rad(obj['inc'])))+3.0*gassigma)
    vs=vs*1.0*2.

    cell=np.mean(proj_plane_pixel_scales(w.celestial))*3600.0
    
    # this transformation follows the whatever defination of "cubecenter" in kinmspy
    px_o=px-float(round(xs/cell))/2.
    py_o=py-float(round(ys/cell))/2.
    pz_o=pz-float(round(vs/abs(dv)))/2.
    if  dv<0: pz_o=pz_o+1.0 # count offset backwards if the z-axis is decreasing in velocity
    px_o_int=round(px_o) ; px_o_frac=px_o-px_o_int
    py_o_int=round(py_o) ; py_o_frac=py_o-py_o_int
    pz_o_int=round(pz_o) ; pz_o_frac=pz_o-pz_o_int
    phasecen=np.array([px_o_frac,py_o_frac])*cell
    voffset=(pz_o_frac)*dv
    
    #start_time = time.time()
    #print(obj)
    #print(cell,xs,ys,vs)
    cube=KinMS(xs,ys,vs,
               cellSize=cell,dv=abs(dv),
               beamSize=1.0,cleanOut=True,
               inc=obj['inc'],
               #sbProf=sbprof,sbRad=sbrad,
               inClouds=inclouds,
               velRad=rad,velProf=velprof,gasSigma=gassigma,
               #ra=obj['xypos'][0],dec=obj['xypos'][1],restFreq=obj['restfreq'],
               vSys=obj['vsys'],
               phaseCen=phasecen,vOffset=voffset,
               #phaseCen=[0,0],vOffset=0,
               fixSeed=fixseed,
               #nSamps=nsamps,fileName=outname+'_'+tag,
               posAng=obj['pa'],
               intFlux=obj['lineflux'])
    
    # cube in units of Jy/pixel * km/s or specifici intensity * km/s
    if  'angstrom' in header['CUNIT3']:
        cube=cube*abs(dv)/(header['CDELT3'])
    #print("--- %s seconds ---" % (time.time() - start_time))
    #   KinMS provide the cube in (x,y,v) shape, but not in the Numpy fasion. transpose required
    #   flip z-axis if dv<0
    #print(cube.shape)
    #size=human_unit(get_obj_size(cube[:,:,:])*u.byte)
    #size=human_to_string(size,format_string='{0:3.0f} {1}')
    #print(size,get_obj_size(deepcopy(cube[:,:,:])),type(cube))
    #print(cube.shape)
    #print(cube.sum())
    
    cube=cube.T
    

            
    if  dv<0: cube=np.flip(cube,axis=0)
    
    if  model is None:
        if  w.naxis==4:
            model_out=np.zeros(w.array_shape)
        if  w.naxis==3:
            model_out=np.zeros((1,)+w.array_shape)
    else:
        model_out=model
    #print(cube.shape,'-->',model.shape)
    model_out=paste_array(model_out,cube[np.newaxis,:,:,:],(0,int(pz_o_int),int(py_o_int),int(px_o_int)),method='add')
    
    size=human_unit(getsizeof(model_out)*u.byte)
    size=human_to_string(size,format_string='{0:3.0f} {1}')
    #print('<<-',size)
    #print(model_out.shape)

    
    model_prof={}
    model_prof['sbrad']=prof1d['sbrad'].copy()
    model_prof['sbprof']=prof1d['sbprof'].copy()
    
    model_prof['vrad']=rad.copy()
    model_prof['vrot']=velprof.copy()
    model_prof['vdis']=gassigma
    
    #model_prof['sbrad_node']=obj['radi'].copy()
    #model_prof['sbprof_node']=obj['radi'].copy()
    model_prof['vrad_node']=np.array(obj['vrad'])
    model_prof['vrot_node']=np.array(obj['vrot'])
    model_prof['vdis_node']=np.array(obj['vdis'])
    if  'vrot_halo' in obj:
        model_prof['vrot_halo_node']=np.array(obj['vrot_halo'])
    if  'vrot_disk' in obj:
        model_prof['vrot_disk_node']=np.array(obj['vrot_disk'])

    if  model is None:
        return model_out,model_prof
    else:
        return model_prof




def model_disk3d_inclouds_pmodel(obj,seed,nSamps=100000,returnprof=True):
    """
    cloudlet generator with a prior morphological assumption 
    """

    w=WCS(obj['pheader']).celestial
    px,py=w.wcs_world2pix(obj['xypos'][0],obj['xypos'][1],0)
    
    cell=np.mean(proj_plane_pixel_scales(w))*3600.0
    

    pmodel_flat=gal_flat(obj['pmodel'],obj['pa'],obj['inc'],cen=(px,py),fill_value=0.0,align_major=True)
    fits.writeto('testx.fits',pmodel_flat,overwrite=True)
    
    sample=pdf2rv_nd(pmodel_flat,size=nSamps,sort=False,interp=True,seed=seed)
    shape=sample.shape

    inClouds=np.zeros((shape[1],3))
    inClouds[:,0]=(sample[0,:]-px)*cell
    inClouds[:,1]=(sample[1,:]-py)*cell
    
    mod = Sersic1D(amplitude=1.0,r_eff=obj['sbser'][0],n=obj['sbser'][1])
    sbRad=np.arange(0.,obj['sbser'][0]*7.0,obj['sbser'][0]/25.0)
    sbProf=mod(sbRad)
    diskThick=0.0
    if  'diskthick' in obj:
        diskThick=obj['diskthick']
    
    # truncate the sb profile
    if  'sbrad_min' in obj:
        sbProf[np.where(sbRad<obj['sbrad_min'])]=0.0
    if  'sbrad_max' in obj:
        sbProf[np.where(sbRad>obj['sbrad_max'])]=0.0      
            
    profile={}
    profile['sbrad']=sbRad
    profile['sbprof']=sbProf    #<--- just a placeholder

    return inClouds,profile
    
    
    
def model_disk3d_inclouds(obj,seed,nSamps=100000,returnprof=True):
    """
    replace the cloudlet generator in KinMSpy.py->kinms_sampleFromArbDist_oneSided();

    Note from KinMSpy()
        inclouds : np.ndarray of double, optional
         (Default value = [])
        If your required gas distribution is not symmetric you
        may input vectors containing the position of the
        clouds you wish to simulate. This 3-vector should
        contain the X, Y and Z positions, in units of arcseconds
        from the phase centre. If this variable is used, then
        `diskthick`, `sbrad` and `sbprof` are ignored.
        Example: INCLOUDS=[[0,0,0],[10,-10,2],...,[xpos,ypos,zpos]]

    This function takes the input radial distribution and generates the positions of
    `nsamps` cloudlets from under it. It also accounts for disk thickness
    if requested. Returns 
    
    Parameters
    ----------
    sbRad : np.ndarray of double
            Radius vector (in units of pixels).
    
    sbProf : np.ndarray of double
            Surface brightness profile (arbitrarily scaled).
    
    nSamps : int
            Number of samples to draw from the distribution.
    
    seed : list of int
            List of length 4 containing the seeds for random number generation.
    
    diskThick : double or np.ndarray of double
         (Default value = 0.0)
            The disc scaleheight. If a single value then this is used at all radii.
            If a ndarray then it should have the same length as sbrad, and will be 
            the disc thickness as a function of sbrad. 

    Returns
    -------
    inClouds : np.ndarray of double
            Returns an ndarray of `nsamps` by 3 in size. Each row corresponds to
            the x, y, z position of a cloudlet. 
    """

    # get sersic profile
    
    mod = Sersic1D(amplitude=1.0,r_eff=obj['sbser'][0],n=obj['sbser'][1])
    
    sbRad=np.arange(0.,obj['sbser'][0]*7.0,obj['sbser'][0]/25.0)
    sbProf=mod(sbRad)
    diskThick=0.0
    if  'diskthick' in obj:
        diskThick=obj['diskthick']
    
    # truncate the sb profile
    if  'sbrad_min' in obj:
        sbProf[np.where(sbRad<obj['sbrad_min'])]=0.0
    if  'sbrad_max' in obj:
        sbProf[np.where(sbRad>obj['sbrad_max'])]=0.0        

    
    # Randomly generate the radii of clouds based on the distribution given by the brightness profile
    pdf_x=abs(sbRad)
    pdf_y=sbProf*2.*np.pi*abs(sbRad)
    r_flat=pdf2rv(pdf_x,pdf_y,seed=seed[0],size=int(nSamps))

    # Generates a random phase around the galaxy's axis for each cloud 
    # with the Fourier Models (not the same as the xy-transform in galfit)
    fm_m=2. if ('fm_m' not in obj) else obj['fm_m']
    fm_frac=0. if ('fm_frac' not in obj) else obj['fm_frac']
    fm_pa=0. if ('fm_pa' not in obj) else obj['fm_pa']
    # in this case, cdf can be analystically written out easily
    if  fm_frac!=0.0:
        nres=10000.   # good enough
        cdf_x=np.arange(nres+1)/nres*2.0*np.pi-np.pi
        cdf_y=fm_frac*np.sin(fm_m*cdf_x)/fm_m+cdf_x
        phi=cdf2rv(cdf_x,cdf_y,size=nSamps,seed=seed[1])+np.deg2rad(fm_pa)
    else:
        rng2=np.random.RandomState(seed[1])
        phi = rng2.random_sample(nSamps) * 2 * np.pi
        
    # Generate the GE effect
    # GE: q=maj/min
    ge_pa=0. if ('ge_pa' not in obj) else obj['ge_pa']
    ge_q=1. if ('ge_q' not in obj) else obj['ge_q']

    if  ge_q>1.:
        phi=phi-np.deg2rad(ge_pa)
        r_flat=r_flat*np.sqrt((np.cos(phi)**2.+np.sin(phi)**2.0/ge_q**2.0))
        phi=np.arctan2(np.sin(phi)/ge_q,np.cos(phi))+np.deg2rad(ge_pa)
    
    """
    # CoordRot - Hyperbolic
    #phi_out=1.0
    #phi=
    #cr_alpha=0.0
    #r_in=1.0
    #r_out=2.0
    #theta_out=200.0
    
    #phi_offset=theta_out*cr_tanh(r_flat,r_in=r_in,r_out=r_out,theta_out=theta_out)\
    #           *(0.5*(r_flat/r_out+1.))**cr_alpha
    #phi=np.deg2rad(phi_offset)+phi
    """

        
    # Find the thickness of the disk at the radius of each cloud
    if  isinstance(diskThick, (list, tuple, np.ndarray)):
        interpfunc2 = interpolate.interp1d(sbRad,diskThick,kind='linear')
        diskThick_here = interpfunc2(r_flat)
    else:
        diskThick_here = diskThick    
    
    #Generates a random (uniform) z-position satisfying |z|<disk_here 
    rng3 = np.random.RandomState(seed[2])       
    zPos = diskThick_here * rng3.uniform(-1,1,nSamps)
    
    #Calculate the x & y position of the clouds in the x-y plane of the disk
    r_3d = np.sqrt((r_flat**2) + (zPos**2))                                                               
    theta = np.arccos(zPos / r_3d)                                                              
    xPos = ((r_3d * np.cos(phi) * np.sin(theta)))                                                        
    yPos = ((r_3d * np.sin(phi) * np.sin(theta)))
    
    
    #transform transform
 
    
    #Generates the output array
    inClouds = np.empty((nSamps,3))
    inClouds[:,0] = xPos
    inClouds[:,1] = yPos
    inClouds[:,2] = zPos

    #return something could be useful
    profile={}
    profile['sbrad']=sbRad
    profile['sbprof']=sbProf
    
    if  returnprof==True:
        return inClouds,profile
    else:
        return inClouds

#@profile
def model_uvsample(xymod3d,xymod2d,xyheader,
                   uvw,phasecenter,
                   uvmodel=None,uvdtype='complex64',
                   average=True,
                   verbose=True):
    """
    simulate the observation in the UV-domain
    The input reference 2D / 3D model (e.g. continuume+line) is expected in units of Jy/pix
    
    uvw shape:           nrecord x 3  
    uvmodel shape:       nrecord x nchan (less likely: nrecord x nchan x ncorr)
    xymodel shape:       nstokes x nchan x ny x nx
    
    note1:
        Because sampleImaging() can be only applied to single-wavelength dataset, we have to loop over
        all channels for multi-frequency dataset (e.g. spectral cubes). This loop operations is typically
        the bottle-neck. To reduce the number of operation, we can only do uvsampling for frequency-plane
        with varying morphology and process frequency-inpdent emission using one operation:  
        the minimal number of operations required  is:
                nplane(with varying morphology) + 1 x sampleImage()
          we already trim any else overhead (e.g. creating new array) and reach close to this limit.
    
    note2:
        when <uvmodel> is provided as input, a new model will be added into the array without additional memory usage 
          the return variable is just a reference of mutable <uvmodel>

    """
    #verbose=True
    #print('3d:',xymod3d is not None)
    #print('2d:',xymod2d is not None)
    
    #print('xymod3d',np.sum(xymod3d))
    #print('xymod2d',np.sum(xymod2d))
    
    cell=np.sqrt(abs(xyheader['CDELT1']*xyheader['CDELT2']))
    nchan=xyheader['NAXIS3']
    nrecord=(uvw.shape)[0]
    
    # + zeros_like vs. zeros()
    #   the memory of an array created by zeros() can allocated on-the-fly
    #   the creation will appear to be faster but the looping+plan initialization may be slightly slower (or comparable?) 
    # + set order='F' as we want to have quick access to each column:
    #   i.a. first dimension is consequential in memory 
    #   this will improve on the performance of picking uvdata from each channel  
    # we force order='F', so the first dimension is continiuous and we can quicky fetch each channel
    # as the information in a single channel is saved in a block  
    if  uvmodel is None:
        uvmodel_out=np.zeros((nrecord,nchan),dtype=uvdtype,order='F')
    else:
        uvmodel_out=uvmodel

    if  verbose==True:
        start_time = time.time()
        print('nchan,nrecord:',nchan,nrecord)    
            
    # assume that CRPIX1/CRPIX2 is at model image "center" floor(naxis/2);
    # which is true for the mock-up/reference model image xyheader 
    # more information on the pixel index /ra-dec mapping, see:
    #       https://mtazzari.github.io/galario/tech-specs.html     
    dRA=np.deg2rad(+(xyheader['CRVAL1']-phasecenter[0].to_value(u.deg)))
    dDec=np.deg2rad(+(xyheader['CRVAL2']-phasecenter[1].to_value(u.deg)))
    #print('<--',dRA,dDec)
    
    phasecenter_sc = SkyCoord(phasecenter[0], phasecenter[1], frame='icrs')
    refimcenter_sc = SkyCoord(xyheader['CRVAL1']*u.deg,xyheader['CRVAL2']*u.deg, frame='icrs')
    dra, ddec = phasecenter_sc.spherical_offsets_to(refimcenter_sc)
    dRA=dra.to_value(u.rad)
    dDec=ddec.to_value(u.rad)
    #print('-->',dRA,dDec)
    
    cc=0
    
    if  average==False:
        # this will account for the effects of varying frequency on the UV sampling position across the bandwidth
        if  xymod3d is not None and xymod2d is not None:
            xymodel=ne.evaluate("a+b",local_dict={"a":xymod3d,"b":xymod2d})
        else:
            xymodel=xymod2d if xymod3d is None else xymod3d
            
        for i in range(nchan):
            if  ne.evaluate("sum(a)",local_dict={'a':xymodel[0,i,:,:]})==0.0:
                continue
            wv=const.c/(xyheader['CDELT3']*i+xyheader['CRVAL3'])
            cc+=1
            ne.evaluate("a+b",
                        local_dict={"a":uvmodel_out[:,i],
                                    "b":sampleImage((xymodel[0,i,:,:]),np.deg2rad(cell),(uvw[:,0]/wv),(uvw[:,1]/wv),                                   
                                                    dRA=dRA,dDec=dDec,PA=0.,check=False,origin='lower')
                                    },
                        casting='same_kind',out=uvmodel_out[:,i])
    else:
        # for a 2-d model (xymodel2d, e.g. continuume), we ignore the U-V coordinated shiffting due to varying frequency.
        if  xymod3d is not None:
            #ss=time.time()
            for i in range(nchan):
                if  ne.evaluate("sum(a)",local_dict={'a':xymod3d[0,i,:,:]})==0.0:
                    continue
                wv=const.c/(xyheader['CDELT3']*i+xyheader['CRVAL3'])
                cc+=1
                ne.evaluate("a+b",
                            local_dict={"a":uvmodel_out[:,i],
                                        "b":sampleImage((xymod3d[0,i,:,:]),
                                                        (np.deg2rad(cell)).astype(np.float32),
                                                        (uvw[:,0]/wv),
                                                        (uvw[:,1]/wv),                                   
                                                        dRA=dRA,dDec=dDec,
                                                        PA=0.,check=False,origin='lower')
                                        },
                            casting='same_kind',out=uvmodel_out[:,i])
                #print("    ",np.deg2rad(cell),np.sum(uvw[:,0]/wv),np.sum(uvw[:,1]/wv))
            #print("---{0:^10} : {1:<8.5f} seconds ---".format('xymod3d',time.time()-ss))
        
        if  xymod2d is not None:
            i0=int(nchan/2.0)
            xymodelsum=xymod2d.sum(axis=(0,2,3))
            xymodel_zscale=xymodelsum/xymodelsum[i0]        
            wv=const.c/(xyheader['CDELT3']*i0+xyheader['CRVAL3'])
            cc+=1
            #ss=time.time()
            uvmodel0=sampleImage((xymod2d[0,i0,:,:]),
                                 (np.deg2rad(cell)).astype(np.float32),
                                 (uvw[:,0]/wv),
                                 (uvw[:,1]/wv),                                   
                                 dRA=dRA.astype(np.float32),dDec=dDec.astype(np.float32),
                                 PA=0.0,check=False,origin='lower')
            #print("---{0:^10} : {1:<8.5f} seconds ---".format('xymod2d-uvsample',time.time()-ss))          
            #ss=time.time()
            print(np.sum(xymod2d[0,i0,:,:]),uvmodel0,dRA.astype(np.float32),dDec.astype(np.float32))
            ne.evaluate('a+b*c',
                        local_dict={"a":uvmodel_out,
                                    "b":np.broadcast_to(uvmodel0[:,np.newaxis],(nrecord,nchan)),
                                    "c":xymodel_zscale},
                        casting='same_kind',out=uvmodel_out)        
            #print("---{0:^10} : {1:<8.5f} seconds ---".format('xymod2d-pop',time.time()-ss))
        
    if  verbose==True:
        print("uvsampling plane counts: ",cc)
        print("---{0:^10} : {1:<8.5f} seconds ---".format('uvsample',time.time()-start_time))
        print("out=in+model:",uvmodel_out is uvmodel)
   
    return uvmodel_out

    """
    #################
    
    #(uvw[:,0]/wv).copy(order='C'),
    #(uvw[:,1]/wv).copy(order='C'),
                                       
    alternative 1: average=True
    uvmodel[:,i]+=sampleImage(xymodel[0,i,:,:],np.deg2rad(cell),
                               #(uvw[:,0]/wv).copy(order='C'),
                               #(uvw[:,1]/wv).copy(order='C'),
                               (uvw[:,0]/wv),
                               (uvw[:,1]/wv),                                   
                               dRA=dRA,dDec=dDec,PA=0,check=False)
    alternative 2:
    ne3
    ne.evaluate("out=a+b",
                local_dict={"a":uvmodel[:,i],
                            "b":sampleImage(xymodel[0,i,:,:],np.deg2rad(cell),(uvw[:,0]/wv),(uvw[:,1]/wv),                                   
                                            dRA=dRA,dDec=dDec,PA=0,check=False),
                            "out":uvmodel[:,i]
                            },
                casting='same_kind')                                          
    
    #################
    
    # alternative 1: average=False
    #     slower than the picked method by 30%
    for i in range(nchan):
        ne.evaluate("a+b*c",
                    local_dict={"a":uvmodel_out[:,i],
                                "b":uvmodel0,
                                "c":xymodel_zscale[i]},
                    casting='same_kind',out=uvmodel_out[:,i])
    # alternative 2:
    ne3.evaluate("out=a + b * c",
                local_dict={"a":uvmodel_out[:,i],
                            "b":uvmodel0,
                            "c":xymodel_zscale[i]},
                casting='safe',out=uvmodel_out[:,i])
    # others:
    uvmodel+=np.broadcast_to(uvmodel0[:,np.newaxis],uvmodel.shape) #okay
    np.add(uvmodel,np.broadcast_to(uvmodel0[:,np.newaxis],uvmodel.shape),out=uvmodel) #same as above
    uvmodel[:,:]=ne.evaluate("a+b",local_dict={"a":uvmodel,"b":np.broadcast_to(uvmodel0[:,np.newaxis],uvmodel.shape)},casting='same_kind') #slow
    ne2
    ne.evaluate("a+b",
                local_dict={"a":uvmodel,"b":np.broadcast_to(uvmodel0[:,np.newaxis],uvmodel.shape)},
                casting='same_kind',out=uvmodel) #fast
    
    ne3
    ne.evaluate("out=a+b",
                local_dict={"a":uvmodel,
                            "b":np.broadcast_to(uvmodel0[:,np.newaxis],uvmodel.shape).copy(),
                            "out":uvmodel},
                casting='safe') #fast        
    
     this is x2 fasfter for an array of (489423, 238)
    np.multiply(uvmodel0,xymodel_zscale[i],out=uvmodel[:,i])
    np.add(uvmodel[:,i],uvmodel0*xymodel_zscale[i],out=uvmodel[:,i])    
    slow: uvmodel_test=np.einsum('i,j->ij',uvmodel0,xymodel_zscale,optimize='greedy',order='C')
    slow: uvmodel_test=uvmodel*xymodel_zscale
    uvmodel+=np.einsum('i,j->ij',uvmodel0,xymodel_zscale,order='F')
    np.einsum('i,j->ij',uvmodel0.astype(np.complex64),xymodel_zscale.astype(np.float32),order='F',out=uvmodel)
    slow: uvmodel_test=uvmodel*xymodel_zscale
    
    ss=time.time()
    print("---{0:^10} : {1:<8.5f} seconds ---".format('timeit',time.time()-ss))                                
    """


def model_convol(data,header,beam=None,psf=None,returnkernel=False,verbose=True,average=False):
    """
        simulate the observation in the image-domain
        input is expected in units of Jy/pix
        output will in the Jy/cbeam or Jy/dbeam if kernel is peaked at unity.
        
        average=True:
        
            the data is assumed to a continuum image even it's a 3D cube.
            we will take the middle plane of 2D data and PSF for one-time convolution, and broadcast the
            results back into 3D with channel-wise flux changes corrected.
            in this way, we can save the plane-by-plane convolution loop.
            
            It should be only used for narrow-band imaging without near galaxy morphology/PSF changes.
            *DO NOT* turn this one for a model including spectral line emission 
        
        the adopted kernel can be returned
        
        note: + we only use cellsize/bmaj/bmin/bpa info from the header.
                so the header doesn't need to match the data "dimension"
              + the function will skip any plane with 0-flux
              + no clear advantage from 3D-FFT vs. 2D-FFT+loop
              + In 2D-FFT+loop, we can selectively choose the usefull planes
              
        TestLog (numpy vs. mkl):
        
            (62, 48, 48)
            (62, 48, 48)
            (58, 48, 48)
            imodel@examples/bx610/bx610.bb2.cube.iter0.image.fits
            data   dim: (1, 238, 105, 105)
            kernel dim: (1, 238, 105, 105)
            ---  simobs   : 1.12489  seconds ---
            convolved plane counts:  96
            imodel@examples/bx610/bx610.bb3.cube.iter0.image.fits
            data   dim: (1, 238, 105, 105)
            kernel dim: (1, 238, 105, 105)
            ---  simobs   : 0.53417  seconds ---
            convolved plane counts:  45
            --- apicall   : 1.96320  seconds ---
            ---  export   : 0.98041  seconds ---
            
            In [43]: execfile('/Users/Rui/Dropbox/Worklib/projects/GMaKE/gmake_test.py')
            (62, 48, 48)
            (62, 48, 48)
            (58, 48, 48)
            imodel@examples/bx610/bx610.bb2.cube.iter0.image.fits
            data   dim: (1, 238, 105, 105)
            kernel dim: (1, 238, 105, 105)
            ---  simobs   : 0.30933  seconds ---
            convolved plane counts:  98
            imodel@examples/bx610/bx610.bb3.cube.iter0.image.fits
            data   dim: (1, 238, 105, 105)
            kernel dim: (1, 238, 105, 105)
            ---  simobs   : 0.12595  seconds ---
            convolved plane counts:  44
            --- apicall   : 0.75084  seconds ---
            ---  export   : 1.02895  seconds ---
              
              
    """

    # the default setting in convolve_fft is optimzed for the precision rather than speed..
    # https://software.intel.com/en-us/articles/mkl-ipp-choosing-an-fft
    # https://software.intel.com/en-us/articles/fft-length-and-layout-advisor
    # http://www.fftw.org/fftw2_doc/fftw_3.html
    convol_fft_pad=False # we don't care about 2^n since the fancy MKL or FFTW is used: 
                         # the optimized radices are 2, 3, 5, 7, and 11.
                         # we will control the imsize when extracting subregion
    convol_complex_dtype=np.complex64   #np.complex128
    #convol_complex_dtype=np.complex256   #np.complex128
    convol_psf_pad=False # psf_pad=True can avoild edge wrap by padding the original image to naxis1+naxis2 (or twice if square)
                         # since our sampling/masking cube already restrict the inner quarter for chi^2, we don't need to pad further.
    
    #w=WCS(header)
    #cell=np.mean(proj_plane_pixel_scales(w.celestial))*3600.0
    cell=np.sqrt(abs(header['CDELT1']*header['CDELT2']))*3600.0


    #   get the convolution Kernel normalized to 1 at PEAK
    #   turn on normalization in convolve() will force the Jy/Pix->Jy/beam conversion
    #   priority: psf>beam>header(2D or 3D KERNEL) 
    
    dshape=data.shape
    
    #   we didn't turn on mode='oversample' since the data pixelization 
    #   is generally oversampling the beam
     
    if  psf is not None:
        kernel=psf.copy()
    elif beam is not None:
        if  not isinstance(beam, (list, tuple, np.ndarray)):
            gbeam = [beam,beam,0]
        else:
            gbeam = beam
        kernel=makekernel(dshape[-1],dshape[-2],
                        [gbeam[0]/cell,gbeam[1]/cell],pa=gbeam[2],
                        mode=None)
    else:
        kernel=makekernel(dshape[-1],dshape[-2],
                        [header['BMAJ']*3600./cell,header['BMIN']*3600./cell],pa=header['BPA'],
                        mode=None)

    if  verbose==True:
        print('data   dim:',data.shape)
        print('kernel dim:',kernel.shape)
        start_time = time.time()

    model=np.zeros(data.shape)
    cc=0
    for i in range(dshape[-3]):

        #   skip blank planes
        if  np.sum(data[0,i,:,:])==0.0:
            continue
        #   skip all-but-one planes if average==True
        if  average==True and i!=int(dshape[-3]/2.0):
            continue
                
        if  kernel.ndim==2:
            kernel_used=kernel
        else:
            kernel_used=kernel[0,i,:,:]
            
        model[0,i,:,:]=convolve_fft(data[0,i,:,:],kernel_used,
                                    fft_pad=convol_fft_pad,psf_pad=convol_psf_pad,
                                    complex_dtype=convol_complex_dtype,
                                    #fftn=np.fft.fftn, ifftn=np.fft.ifftn,
                                    fftn=mkl_fft.fftn, ifftn=mkl_fft.ifftn,
                                    #nan_treatment='fill',fill_value=0.0,
                                    #fftn=scipy.fftpack.fftn, ifftn=scipy.fftpack.ifftn,
                                    #fftn=pyfftw.interfaces.numpy_fft.fftn, ifftn=pyfftw.interfaces.numpy_fft.ifftn,
                                    normalize_kernel=False)

        cc=cc+1
    
    if  average==True:
        
        i0=int(dshape[-3]/2.0)
        model0=model[0,i0,:,:]
        data0sum=data[0,i0,:,:].sum()
        
        for i in range(dshape[-3]):
            if  data0sum!=0.0:
                model[0,i,:,:]=model0*(data[0,i,:,:]).sum()/data0sum
    

    if  verbose==True:
        
        print("convolved plane counts: ",cc)
        print("---{0:^10} : {1:<8.5f} seconds ---".format('convol',time.time()-start_time))
        #start_time = time.time()
        #test1=(data[0,:,:,:])
        #test2=(kernel[np.newaxis,0,100,(52-10):(52+10),(52-10):(52+10)])
        #print(test1.shape,test2.shape)
        #test=convolve(test1,test2)
        #print("---{0:^10} : {1:<8.5f} seconds ---".format('simobs-beta',time.time()-start_time))
        

    if  returnkernel==True:
        return model,kernel
    else:
        return model



    


    
if  __name__=="__main__":

    """
    examples
    """
    pass


from .utils import *
from .model_func_kinms import *
from .model_func import *

from galario.single import sampleImage

from io import StringIO
from asteval import Interpreter
import astropy.units as u
from astropy.coordinates import Angle
from astropy.coordinates import SkyCoord
aeval = Interpreter(err_writer=StringIO())
aeval.symtable['u']=u
aeval.symtable['SkyCoord']=SkyCoord

from sys import getsizeof
from .utils import human_unit
from .utils import human_to_string

import scipy.constants as const
from astropy.modeling.models import Gaussian2D
from astropy.modeling.models import Sersic1D
from astropy.modeling.models import Sersic2D
from astropy.convolution import discretize_model
from astropy.wcs import WCS

from copy import deepcopy

from scipy.interpolate import interp1d

from astropy.wcs.utils import proj_plane_pixel_area, proj_plane_pixel_scales
import numexpr as ne
import fast_histogram
import time
#import gc

from memory_profiler import profile

    
@profile    
def model_disk2d2(header,objp,
                  model=[],
                  factor=5):
    """
    insert a continuum model (frequency-independent) into a 2D image or 3D cube
    
    header:    data header including WCS
    
    ra,dec:    object center ra/dec
    ellip:     1-b/a
    posang:    in the astronomical convention
    r_eff:     in arcsec
    n:         sersic index
    
    intflux:   Jy
    restfreq:  GHz
    alpha:     
    
    co-centeral point souce: pintflux=0.0
    
    the header is assumed to be ra-dec-freq-stokes

    note:
        since the convolution is the bottom-neck, a plane-by-plane processing should
        be avoided.
        avoid too many header->wcs / wcs-header calls
        1D use inverse transsforming
    
    return model in units of Jy/pix  
    
    note:    now we return model in the native forms rather than gridded cubes (which can be large)
    return form (componnet_name,im2d,scaling_vector,ox,oy mapping to fudicual grid)
    
    """

    obj=obj_defunit(objp)
    
    #   translate to dimensionless numerical value in default units

    ra=obj['xypos'][0]
    dec=obj['xypos'][1]
    r_eff=obj['sbser'][0]
    n=obj['sbser'][1]
    posang=obj['pa']
    ellip=1.-np.cos(np.deg2rad(obj['inc']))
    pintflux=0.0
    if  'pcontflux' in obj:
        pintflux=obj['pcontflux']    
    intflux=obj['contflux']
    restfreq=obj['restfreq']
    alpha=3.0
    if  'alpha' in obj:
        alpha=obj['alpha']
    
    #   build objects
    #   use np.meshgrid and don't worry about transposing
    w=WCS(header)
    cell=np.mean(proj_plane_pixel_scales(w.celestial))*3600.0
    #px,py=skycoord_to_pixel(SkyCoord(ra,dec,unit="deg"),w,origin=0) # default to IRCS
    px,py,pz,ps=(w.wcs_world2pix(ra,dec,0,0,0))
    vz=np.arange(header['NAXIS3'])
    wz=(w.wcs_pix2world(0,0,vz,0,0))[2]

    #   get 2D disk model
    mod = Sersic2D(amplitude=1.0,r_eff=r_eff/cell,n=n,x_0=px,y_0=py,
               ellip=ellip,theta=np.deg2rad(posang+90.0))
    xs_hz=int(r_eff/cell*7.0)
    ys_hz=int(r_eff/cell*7.0)
    #   use discretize_model(mode='oversample') 
    #       discretize_model(mode='center') or model2d=mod(x,y) may lead worse precision
    
    #   x,y = np.meshgrid(np.arange(header['NAXIS1']), np.arange(header['NAXIS2']))
    #   model2d=mod(x,y)

    #   intflux at different planes / broadcasting to the data dimension
    intflux_z=(wz/1e9/restfreq)**alpha*intflux    
    
    #option 1
    
    px_o_int=round(px-xs_hz)
    py_o_int=round(py-ys_hz)
    model2d=discretize_model(mod,
                             (px_o_int,px_o_int+2*xs_hz+1),
                             (py_o_int,py_o_int+2*ys_hz+1),
                             mode='oversample',factor=factor)
    model2d/=model2d.sum()
    print('2d',get_obj_size(model2d,to_string=True))
    #model2d=model2d[np.newaxis,np.newaxis,:,:]*intflux_z[np.newaxis,:,np.newaxis,np.newaxis]
    
    #component=
    model.append(('disk2d',model2d,intflux_z,int(px_o_int),int(py_o_int)))
    if  pintflux!=0.0:        
        model.append(('disk2d',np.ones((1,1)),(wz/1e9/restfreq)**alpha*pintflux,int(np.round(px)),int(np.round(py))))
    
    return 

def model_disk3d2(header,objp,
                 model=[],
                 nsamps=100000,decomp=False,fixseed=False,
                 verbose=False,
                 mod_dct=None):
    """
    handle modeling parameters to kinmspy and generate the model cubes embeded into 
    a dictionary nest
    
    note:
        kinmspy can only construct a spectral cube in the ra-dec-vel space. We use kinmspy
        to construct a xyv cube with the size sufficient to cover the model object. Then 
        we insert it into the data using the WCS/dimension info. 
    """    

    #######################################################################
    #   WORLD ----      DATA        ----    MODEL
    #######################################################################
    #   ra    ----      xi_data     ----    xSize/2.+phasecen[0]/cell
    #   dec   ----      yi_data     ----    ySize/2.+phasecen[1]/cell
    #   vsys  ----      vi_data     ----    vSize/2.+voffset/dv
    #
    # collect the world coordinates of the disk center (ra,dec,freq/wave)
    # note: vsys is defined in the radio(freq)/optical(wave) convention, 
    #       within the rest frame set at obj['z']/
    #       the convention doesn't really matter, as long as vsys << c
    #######################################################################
    #   vector description of the z-axis (data in Hz or m/s; model in km/s)
    #   rfreq=obj['restfreq']/(1.0+obj['z'])            # GHz (obs-frame)
    #   fsys=(1.0-obj['vsys']/(const.c/1000.0))*rfreq   # line systematic frequency (obs-frame)
    #   follow the convention / units defined in WCS:
    #   https://arxiv.org/pdf/astro-ph/0207407.pdf
    #   http://dx.doi.org/10.1051/0004-6361/201015362
    #   https://www.atnf.csiro.au/people/mcalabre/WCS/wcslib/wcsunits_8h.html#a25ba0f0129e88c6e7c74d4562cf796cd
    
    
    
    obj=obj_defunit(objp)
    #pprint(obj)
    
    w=WCS(header)
    if  'Hz' in header['CUNIT3']:
        wz=obj['restfreq']*1e9/(1.0+obj['z'])*(1.-obj['vsys']*1e3/const.c)
        dv=-const.c*header['CDELT3']/(1.0e9*obj['restfreq']/(1.0+obj['z']))/1000.
    if  'angstrom' in header['CUNIT3']:
        wz=obj['restwave']*(1.0+obj['z'])*(1.+obj['vsys']*1e3/const.c)/1e10
        dv=const.c*header['CDELT3']/(obj['restwave']*(1.0+obj['z']))/1000.
    if  'm/s' in header['CUNIT3']:
        wz=obj['vsys']*1000.
        dv=header['CDELT3']/1000.        
    #   wz: in hz / m or m.s
    #   dv: km/s
    
    #   get 0-based pix-index
    if  w.naxis==4:
        px,py,pz,ps=w.wcs_world2pix(obj['xypos'][0],obj['xypos'][1],wz,1,0)
    if  w.naxis==3:
        px,py,pz=w.wcs_world2pix(obj['xypos'][0],obj['xypos'][1],wz,0)
    #print(wz)
    #print(">>>>>>",(0,px,py,pz))
    ####
    #   About KinMS:
    #       + cube needs to be transposed to match the fits.data dimension 
    #       + the WCS/FITSIO in KINMSPY is buggy/offseted: don't use it
    #       + turn off convolution in kinmspy
    #       + KinMS only works in the RA/DEC/VELO domain.
    #       + KinMS is not preicse for undersampling SBPROFILE/VROT (linear interp -> integral)
    #           - we feed an oversampling vector to kinMS here.
    ####
    
    #####################
    
    #   build an oversampled SB vector.
    
    #mod = Sersic1D(amplitude=1.0,r_eff=obj['sbser'][0],n=obj['sbser'][1])
    #sbprof=mod(sbrad)
    
    #print(sbrad)
    #print(np.array(obj['radi']))
    #velrad=obj['radi']
    #velprof=obj['vrot']
    #gassigma=np.array(obj['vdis'])
    
    #   only extend to this range in vrot/sbprof
    #   this is the fine radii vector fed to kinmspy

    nsamps=int(nsamps)
    if  fixseed==True:
        seeds=[100,101,102,103]
    else:
        seeds=np.random.randint(0,100,4)
        # seeds[0] -> rad
        # seeds[1] -> phi
        # seeds[2] -> z
        # seeds[3] -> v_sigma    
    
    if  obj['pmodel'] is None:
        inclouds,prof1d=model_disk3d_inclouds(obj,seeds,nSamps=nsamps)
        rad=np.arange(0.,obj['sbser'][0]*7.0,obj['sbser'][0]/25.0)
    else:
        inclouds,prof1d=model_disk3d_inclouds_pmodel(obj,seeds,nSamps=nsamps)
        rad=np.arange(0.,np.nanmax(np.sqrt(inclouds[:,0]**2+inclouds[:,1]**2))+obj['sbser'][0]/25.0,obj['sbser'][0]/25.0)
    
    ikind='cubic'  # bad for extraplate but okay for interplate 'linear'/'quadratic'
    print(rad)
    if  isinstance(obj['vrot'], (list, np.ndarray)):
        if_vrot=interp1d(np.array(obj['vrad']),np.array(obj['vrot']),kind=ikind,bounds_error=False,fill_value=(obj['vrot'][0],obj['vrot'][-1]))
        velprof=if_vrot(rad)
    if  isinstance(obj['vrot'], tuple):
        if  obj['vrot'][0].lower()=='dynamics':
            velprof=model_dynamics(obj,mod_dct[obj['vrot'][1]],rad)
        elif  obj['vrot'][0].lower()=='arctan':
            velprof=obj['vrot'][1]*2.0/np.pi*np.arctan(rad/obj['vrot'][2])
        elif  obj['vrot'][0].lower()=='exp':
            velprof=obj['vrot'][1]*(1-np.exp(-rad/obj['vrot'][2]))
        elif  obj['vrot'][0].lower()=='tanh':
            velprof=obj['vrot'][1]*np.tanh(rad/obj['vrot'][2])
        else:
            for ind in range(1,len(obj['vrot'])):
                aeval.symtable["p"+str(ind)]=obj['vrot'][ind]
                aeval.symtable["vrad"]=rad
            velprof=aeval(obj['vrot'][0])
    
    if  isinstance(obj['vdis'], (list, tuple, np.ndarray)):
        if_vdis=interp1d(np.array(obj['vrad']),np.array(obj['vdis']),kind=ikind,bounds_error=False,fill_value=(obj['vdis'][0],obj['vdis'][-1]))
        gassigma=if_vdis(rad)
    else:
        gassigma=rad*0.0+obj['vdis']
        obj['vdis']=np.array(obj['vrad'])*0.0+obj['vdis']
        
        
        
    
    """
    #   same as above
    if_vrot=interpolate.UnivariateSpline(np.array(obj['radi']),np.array(obj['vrot']),s=1.0,ext=3)
    velprof=if_vrot(velrad)
    #   not good for RC
    if_vrot=interp1d(np.array(obj['radi']),np.array(obj['vrot']),kind=ikind,bounds_error=False,fill_value='extrapolate')
    if_vdis=interp1d(np.array(obj['radi']),np.array(obj['vdis']),kind=ikind,bounds_error=False,fill_value='extrapolate')
    velprof=if_vrot(velrad)
    gassigma=if_vdis(velrad)    
    """

    
    ####################
    
    xs=np.max(rad)*1.0*2.0
    ys=np.max(rad)*1.0*2.0
    vs=np.max(velprof*np.abs(np.sin(np.deg2rad(obj['inc'])))+3.0*gassigma)
    vs=vs*1.0*2.

    cell=np.mean(proj_plane_pixel_scales(w.celestial))*3600.0
    
    # this transformation follows the whatever defination of "cubecenter" in kinmspy
    px_o=px-float(round(xs/cell))/2.
    py_o=py-float(round(ys/cell))/2.
    pz_o=pz-float(round(vs/abs(dv)))/2.
    if  dv<0: pz_o=pz_o+1.0 # count offset backwards if the z-axis is decreasing in velocity
    px_o_int=round(px_o) ; px_o_frac=px_o-px_o_int
    py_o_int=round(py_o) ; py_o_frac=py_o-py_o_int
    pz_o_int=round(pz_o) ; pz_o_frac=pz_o-pz_o_int
    phasecen=np.array([px_o_frac,py_o_frac])*cell
    voffset=(pz_o_frac)*dv
    
    #start_time = time.time()
    #print(obj)
    #print(cell,xs,ys,vs)
    clouds=KinMS2(xs,ys,vs,
               cellSize=cell,dv=abs(dv),
               beamSize=1.0,cleanOut=True,
               inc=obj['inc'],
               #sbProf=sbprof,sbRad=sbrad,
               inClouds=inclouds,
               velRad=rad,velProf=velprof,gasSigma=gassigma,
               #ra=obj['xypos'][0],dec=obj['xypos'][1],restFreq=obj['restfreq'],
               vSys=obj['vsys'],
               phaseCen=phasecen,vOffset=voffset,
               #phaseCen=[0,0],vOffset=0,
               fixSeed=fixseed,
               #nSamps=nsamps,fileName=outname+'_'+tag,
               posAng=obj['pa'],
               intFlux=obj['lineflux'])
    
    #int(pz_o_int),int(py_o_int),int(px_o_int)
    
    model.append(('disk3d',)+clouds+(int(px_o_int),int(py_o_int),int(pz_o_int)))

    
    model_prof={}
    model_prof['sbrad']=prof1d['sbrad'].copy()
    model_prof['sbprof']=prof1d['sbprof'].copy()
    
    model_prof['vrad']=rad.copy()
    model_prof['vrot']=velprof.copy()
    model_prof['vdis']=gassigma
    
    #model_prof['sbrad_node']=obj['radi'].copy()
    #model_prof['sbprof_node']=obj['radi'].copy()
    model_prof['vrad_node']=np.array(obj['vrad'])
    model_prof['vrot_node']=np.array(obj['vrot'])
    model_prof['vdis_node']=np.array(obj['vdis'])
    if  'vrot_halo' in obj:
        model_prof['vrot_halo_node']=np.array(obj['vrot_halo'])
    if  'vrot_disk' in obj:
        model_prof['vrot_disk_node']=np.array(obj['vrot_disk'])

    return model_prof
                             

#@profile
def model_uvchi2(imodel,xyheader,
                    uvdata,uvw,phasecenter,uvweight,uvflag,
                    average=True,verbose=True):
    """
    simulate the observation in the UV-domain
    The input reference 2D / 3D model (e.g. continuume+line) is expected in units of Jy/pix
    
    uvw shape:           nrecord x 3  
    uvmodel shape:       nrecord x nchan (less likely: nrecord x nchan x ncorr)
    xymodel shape:       nstokes x nchan x ny x nx
    
    note1:
        Because sampleImaging() can be only applied to single-wavelength dataset, we have to loop over
        all channels for multi-frequency dataset (e.g. spectral cubes). This loop operations is typically
        the bottle-neck. To reduce the number of operation, we can only do uvsampling for frequency-plane
        with varying morphology and process frequency-inpdent emission using one operation:  
        the minimal number of operations required  is:
                nplane(with varying morphology) + 1 x sampleImage()
          we already trim any else overhead (e.g. creating new array) and reach close to this limit.
    
    note2:
        when <uvmodel> is provided as input, a new model will be added into the array without additional memory usage 
          the return variable is just a reference of mutable <uvmodel>

    """

    #print('3d:',imodel is not None)
    #print('2d:',xymod2d is not None)
    
    cell=np.sqrt(abs(xyheader['CDELT1']*xyheader['CDELT2']))
    nchan=xyheader['NAXIS3']
    nrecord=(uvw.shape)[0]
    
    # + zeros_like vs. zeros()
    #   the memory of an array created by zeros() can allocated on-the-fly
    #   the creation will appear to be faster but the looping+plantu initialization may be slightly slower (or comparable?) 
    # + set order='F' as we want to have quick access to each column:
    #   i.a. first dimension is consequential in memory 
    #   this will improve on the performance of picking uvdata from each channel  
    # we force order='F', so the first dimension is continiuous and we can quicky fetch each channel
    # as the information in a single channel is saved in a block  


    if  verbose==True:
        start_time = time.time()
        print('nchan,nrecord:',nchan,nrecord)    
            
    # assume that CRPIX1/CRPIX2 is at model image "center" floor(naxis/2);
    # which is true for the mock-up/reference model image xyheader 
    # more information on the pixel index /ra-dec mapping, see:
    #       https://mtazzari.github.io/galario/tech-specs.html     
    #dRA=np.deg2rad(+(xyheader['CRVAL1']-phasecenter[0].to_value(u.deg)))
    #dDec=np.deg2rad(+(xyheader['CRVAL2']-phasecenter[1].to_value(u.deg)))
    
    dRA=np.deg2rad(+(xyheader['CRVAL1']-phasecenter[0].to_value(u.deg)))
    dDec=np.deg2rad(+(xyheader['CRVAL2']-phasecenter[1].to_value(u.deg)))
    #print('<--',dRA,dDec)
    
    phasecenter_sc = SkyCoord(phasecenter[0], phasecenter[1], frame='icrs')
    refimcenter_sc = SkyCoord(xyheader['CRVAL1']*u.deg,xyheader['CRVAL2']*u.deg, frame='icrs')
    dra, ddec = phasecenter_sc.spherical_offsets_to(refimcenter_sc)    
    dRA=dra.to_value(u.rad)
    dDec=ddec.to_value(u.rad)
    #print('-->',dRA,dDec)
    
    cc=0
    chi2=0

    for i in range(nchan):
        
        wv=const.c/(xyheader['CDELT3']*i+xyheader['CRVAL3'])
        cc+=1
        plane=np.zeros((xyheader['NAXIS2'],xyheader['NAXIS1']),dtype=np.float32)
        
        for j in range(len(imodel)):
            if  imodel[j][0]=='disk3d':
                model_type,clouds2do,xSize,ySize,vSize,scale,px_o_int,py_o_int,pz_o_int=imodel[j]
                #plane0,edges=np.histogramdd(clouds2do[subs,:],bins=(xSize,ySize,1),range=((0,xSize),(0,ySize),(j,j+1)))
                #subs=np.where( ne.evaluate('(a>=i) & (a<i+1)',local_dict={'a':clouds2do[:,2],'i':i}) )
                subs=np.where( (clouds2do[:,2]>=i) & (clouds2do[:,2]<i+1) )
                if  len(subs[0])>0:
                    #plane0,xedges,yedges=np.histogram2d(clouds2do[subs[0],0],clouds2do[subs[0],1],
                    #                                bins=[xSize,ySize],range=[[0,xSize],[0,ySize]])
                    plane0=fast_histogram.histogram2d(clouds2do[subs[0],0],clouds2do[subs[0],1],
                                                      bins=[int(xSize),int(ySize)],
                                                      range=[[0,xSize],[0,ySize]])
                    plane0=plane0.T #(quick fix)
                    #print(plane.shape,plane0.shape,py_o_int,px_o_int)                            
                    plane=paste_array(plane,plane0*scale,(py_o_int,px_o_int),method='add')
            if  imodel[j][0]=='disk2d':
                model_type,model2d,intflux_z,px_o_int,py_o_int=imodel[j]
                model2d*=intflux_z[j]
                plane=paste_array(plane,model2d,(py_o_int,px_o_int),method='add') 
            if  np.sum(plane)!=0:        
                delta_uv=ne.evaluate('a-b',
                                 local_dict={'a':sampleImage(plane,
                                                        (np.deg2rad(cell)).astype(np.float32),
                                                        (uvw[:,0]/wv),
                                                        (uvw[:,1]/wv),                                   
                                                        dRA=dRA,dDec=dDec,
                                                        PA=0.,check=False,origin='lower'),
                                             'b':uvdata[:,i]})
            else:
                delta_uv=uvdata[:,i]
            chi2+=ne.evaluate('sum( ( (a.real)**2+(a.imag)**2 ) * (~b*c) )', #'sum( abs(a)**2*c)'
                             local_dict={'a':delta_uv,
                                         'b':uvflag[:,i],
                                         'c':uvweight})
                
    return chi2


    
if  __name__=="__main__":

    """
    examples
    """
    pass