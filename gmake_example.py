
execfile('gmake_init.py')


def gmake_example_bx610(version,bbs=['bb1','bb2','bb3','bb4']):


    version='xyb4dm128ab'
    version='xyb4dm128ab_rc'
    version='xyb6dm128ab'
    #version='xyb6dm128ab_rc'

    #version='xyb4dm128lm'
    version='xyb4dm128lmgs'
    #inp_dct=gmake_read_inp('examples/bx610/'+version+'.inp',verbose=False)
    #dat_dct=gmake_read_data(inp_dct,verbose=True,fill_mask=True,fill_error=True)
    #fit_dct,sampler=gmake_fit_setup(inp_dct,dat_dct)
    #gmake_fit_iterate(fit_dct,sampler,nstep=500)

    
    
    outfolder='examples/bx610/models/'+version
    #gmake_fit_analyze(outfolder,burnin=4)
    #result=gmake_lmfit_analyze_nelder(outfolder)
    gmake_fit_analyze(outfolder)
    
    #return result
    
    # 
    """
    
    fn_name_tmp='examples/bx610/models/'+version+'/p_fits/data_bbx.fits'
    #fn_name_tmp='b4cloud/data_bbx.fits'
    for bb in bbs:
        
        fn_name=fn_name_tmp.replace('bbx',bb)
        linechan=None
        if  bb=='bb2' and 'b4' not in fn_name:
            linechan=[(250.964*u.GHz,251.448*u.GHz),(251.847*u.GHz,252.246*u.GHz)]
        if  bb=='bb3' and 'b4' not in fn_name:
            linechan=(233.918*u.GHz,234.379*u.GHz)  
        if  bb=='bb1' and 'b4' in fn_name:
            linechan=(153.069*u.GHz,153.522*u.GHz)
        if  bb=='bb3' and 'b4' in fn_name:
            linechan=(143.359*u.GHz,143.835*u.GHz)

        cen1='icrs; circle( 356.5393256478768,12.82201783168984,1.00") # text={cen1}'
        cen2='icrs; circle( 356.5393256478768,12.82201783168984,0.20") # text={cen2}'
        slice1='icrs; box( 356.5393256478768,12.82201783168984,0.20",0.75",128) # text={slice1}'
        slice2='icrs; box( 356.5393256478768,12.82201783168984,0.20",0.75",38)  # text={slice2}'
        rois=[cen1,cen2,slice1,slice2]
        for roi in rois:
            print('plots_spec1d: ',fn_name)
            gmake_plots_spec1d(fn_name,roi=roi)

        print('plots_mom0xy: ',fn_name)
        gmake_plots_mom0xy(fn_name,linechan=linechan)
     
        pa=-52
        #gmake_plots_makeslice(fn_name,
        #                      radec=[356.5393256478768,12.82201783168984],
        #                      width=0.5,length=2.5,pa=-52,linechan=linechan)
        #gmake_plots_slice(fn_name,i=1)
        #gmake_plots_slice(fn_name,i=2)        

        gmake_plots_radprof(fn_name)
    
    """
    
if  __name__=="__main__":
    

    ####################################
    #   EXAMPLES
    ####################################

    #version='xyb4dm128ab'
    #version='xyb4dm128ab_rc'
    version='xyb6dm128ab'
    #version='xyb6dm128ab_rc'
    version='xyb4dm128lm'
    result=gmake_example_bx610(version)
  
    
        ####################################
    #   EMCEE
    ####################################
    
    """
    #   build a dict holding input config
    #   build a dict holding data
    #   build the sampler and a dict holding sampler metadata
    #inp_dct=gmake_read_inp('examples/bx610/bx610xy_dm64_all.inp',verbose=False)
    #inp_dct=gmake_read_inp('examples/bx610/bx610xy_cm64_all.inp',verbose=False)
    #inp_dct=gmake_read_inp('examples/bx610/bx610xy_band4_cm64_all.inp',verbose=False)
    inp_dct=gmake_read_inp('examples/bx610/bx610xy_nas_cm64_all.inp',verbose=False)
    #inp_dct=gmake_read_inp('examples/bx610/bx610xy_cm_cont.inp',verbose=False)
    #inp_dct=gmake_read_inp('examples/bx610/bx610xy_dm_cont.inp',verbose=False)
    dat_dct=gmake_read_data(inp_dct,verbose=True,fill_mask=True,fill_error=True)
    fit_dct,sampler=gmake_emcee_setup(inp_dct,dat_dct)
    gmake_emcee_iterate(sampler,fit_dct,nstep=1000)

    outfolder='bx610xy_nas_cm64_all_emcee'
    fit_tab=gmake_emcee_analyze(outfolder,plotsub=None,burnin=600,plotcorner=True,
                    verbose=True)
    fit_dct=np.load(outfolder+'/fit_dct.npy').item()
    inp_dct=np.load(outfolder+'/inp_dct.npy').item()
    dat_dct=np.load(outfolder+'/dat_dct.npy').item()
    fit_tab=Table.read(outfolder+'/'+'emcee_chain_analyzed.fits')
    theta=fit_tab['p_start'].data[0]
    lnl,blobs=gmake_model_lnprob(theta,fit_dct,inp_dct,dat_dct,savemodel=outfolder+'/p_start')
    print('pstart:    ',lnl,blobs)     
    theta=fit_tab['p_median'].data[0]
    lnl,blobs=gmake_model_lnprob(theta,fit_dct,inp_dct,dat_dct,savemodel=outfolder+'/p_median')
    print('p_median: ',lnl,blobs)
    """
