PRO HZDYN_BX610_SUBREG_2015_ALL


repo='/Volumes/D1/projects/hzdyn/2015.1.00250.S/science_goal.uid___A001_X2fe_X20d/group.uid___A001_X2fe_X20e/member.uid___A001_X2fe_X20f/imaging/'
repo='/Volumes/D1/projects/hzdyn/2013.1.00059.S/science_goal.uid___A001_X12b_X239/group.uid___A001_X12b_X23a/member.uid___A001_X12b_X23b/imaging/'
itype='cube'
itype='mfs'
iter='itern'
iter='iter0'
tag='64x64'
nxy=64
tag='128x128'
nxy=128
HZDYN_BX610_SUBREG_2015,repo,itype,iter,tag,nxy
HZDYN_BX610_SUBREG_2015_MASK,itype,iter,tag
HZDYN_BX610_SUBREG_2015_HEXSAMPLE,itype,iter,tag

END

PRO HZDYN_BX610_SUBREG_2015,repo,itype,iter,tag,nxy

;repo='/Volumes/D1/projects/hzdyn/2015.1.00250.S/science_goal.uid___A001_X2fe_X20d/group.uid___A001_X2fe_X20e/member.uid___A001_X2fe_X20f/imaging/'
;for i=0,n_elements(input)-1 do begin
;    im=readfits(export_dir+input[i],hd)
;    hextractx,im,hd,subim,subhd,[-1.,1.]*2.0,[-1.,1.]*2.0,radec=[356.53929,12.822]
;    writefits,'bx610_'+output_tag[i]+'.fits',subim,subhd
;endfor


if  itype eq 'cube' then begin
    input_temp='*bbx*ro1_nm.'+itype+'/bx610.'+iter+'.image.fits.gz'
endif
if  itype eq 'mfs' then begin
    input_temp='*bbx*ro1_nm.'+itype+'/bx610.'+iter+'.image.tt0.fits.gz'
endif
output_temp='bx610.bbx.'+itype+tag+'.'+iter+'.image.fits'

for i=0,3 do begin
    input=repstr(input_temp,'bbx','bb'+strtrim(i+1,2))
    im=readfits(repo+input,hd)
    
    ;hextractx,im,hd,subim,subhd,[-1.,1.]*2.0,[-1.,1.]*2.0,radec=[356.5393354,12.8220249]
    adxy,hd,356.5393354,12.8220249,xc,yc
    hextract3d,im,hd,subim,subhd,[xc-nxy/2,xc+nxy/2-1,yc-nxy/2,yc+nxy/2-1]
   
    output=repstr(output_temp,'bbx','bb'+strtrim(i+1,2))
    writefits,output,subim,subhd
endfor


for i=0,3 do begin
    input=repstr(input_temp,'bbx','bb'+strtrim(i+1,2))
    input=repstr(input,'.image.','.psf.')
    im=readfits(repo+input,hd)
    loc=where(im eq max(im,/nan))
    loc=loc[0]
    ind = ARRAY_INDICES(im, loc)
    ;hsize=52
    ;hextract3d,im,hd,subim,subhd,[ind[0]-hsize,ind[0]+hsize,ind[1]-hsize,ind[1]+hsize]
    hextract3d,im,hd,subim,subhd,[ind[0]-nxy/2,ind[0]+nxy/2-1,ind[1]-nxy/2,ind[1]+nxy/2-1]
    
    output=repstr(output_temp,'bbx','bb'+strtrim(i+1,2))
    output=repstr(output,'.image.','.psf.')
    writefits,output,subim,subhd
endfor

END

PRO HZDYN_BX610_SUBREG_2015_MASK,itype,iter,tag


input_temp='bx610.bbx.'+itype+tag+'.'+iter+'.image.fits'

for i=0,3 do begin
    input=repstr(input_temp,'bbx','bb'+strtrim(i+1,2))
    im=readfits(input,hd)
    mk=im*0.0
    ;mk[(64-32):(64+32),(64-32):(64+32),*]=1.0
    mk[*,*,*]=1.0
    writefits,repstr(input,'.image','.mask'),mk,hd
    unc=im*0.0
    unc=unc+robust_sigma(im)
    writefits,repstr(input,'.image','.unc'),unc,hd
endfor

END

PRO HZDYN_BX610_SUBREG_2015_HEXSAMPLE,itype,iter,tag

;hexsample_bx610,'bx610_spw27',356.53929,12.822,xlimit=[33.-10.,60.+10.],ylimit=[40.-10.,64.+10.]

;tag='128x128'
;tag='128x128_ro0'
;xlimit0=[32.-18,32.+18]
;ylimit0=[32.-18,32.+18]

hexsample_bx610,'bx610.bb1.'+itype+tag+'.'+iter,356.5393354,12.8220249;,xlimit=xlimit0,ylimit=ylimit0
hexsample_bx610,'bx610.bb2.'+itype+tag+'.'+iter,356.5393354,12.8220249;,xlimit=xlimit0,ylimit=ylimit0
hexsample_bx610,'bx610.bb3.'+itype+tag+'.'+iter,356.5393354,12.8220249;,xlimit=xlimit0,ylimit=ylimit0
hexsample_bx610,'bx610.bb4.'+itype+tag+'.'+iter,356.5393354,12.8220249;,xlimit=xlimit0,ylimit=ylimit0

END


PRO HEXSAMPLE_BX610,prefix,cra,cdec,spacing=spacing,ratio=ratio,bpa=bpa,xlimit=xlimit,ylimit=ylimit

im=prefix+'.image.fits'
im=readfits(im,hd)

mk=readfits(prefix+'.mask.fits',mhd)



RADIOHEAD,hd,s=s
getrot,hd,rotang,cdelt
psize=abs(cdelt[0]*60.*60.)
sz=size(im,/d)
ctr=round(sz/2)
adxy,hd,cra,cdec,cx,cy



if  n_elements(spacing) eq 0 then spacing=s.bmaj/psize
if  n_elements(ratio) eq 0 then ratio=s.bmaj/s.bmin
if  n_elements(bpa) eq 0 then bpa=s.bpa
if  n_elements(xlimit) ne 2 then xlimit=[0,sz[0]-1]
if  n_elements(ylimit) ne 2 then ylimit=[0,sz[1]-1]

print,spacing,ratio,bpa

sample_grid,[cx,cy],spacing,/hex,$
    ratio=ratio,ang=bpa,$
    xout=xout,yout=yout,x_limit=xlimit,y_limit=ylimit
;tag=where(xout gt  and xout lt sz[0]-10 and yout gt 10 and yout lt sz[1]-10 )
;xout=xout[tag]
;yout=yout[tag]
xyad,hd,xout,yout,outra,outdec

if  n_elements(sz) eq 2 then nc=1 else nc=sz[2]

print,n_elements(xout)

hex_ind=MAKE_ARRAY(3,n_elements(xout)*nc)
for i=0,n_elements(xout)-1 do begin
    hex_ind[0,(i*nc+0):(i*nc+nc-1)]=xout[i]
    hex_ind[1,(i*nc+0):(i*nc+nc-1)]=yout[i]
    hex_ind[2,(i*nc+0):(i*nc+nc-1)]=findgen(nc)
endfor

hex={sp_ra:outra,sp_dec:outdec,sp_index:hex_ind}
mwrfits,hex,prefix+'.hex_tb.fits',/create


xout=round(xout)
yout=round(yout)
;print,xout
;print,yout
imhex=im*0.0
imhex0=im[*,*,0]*0.0
imhex0[xout,yout]=1.0
for i=0,nc-1 do begin
    imhex[*,*,i]=imhex0
endfor
print,'npix:',total(imhex)

writefits,prefix+'.hex_im.fits',imhex,hd

END

PRO HZDYN_BX610_SUBREG_2015_MOM0

;   working in alma/band4 dir
pickband='band4'
nline=2
;   working in alma/band6 dir
;pickband='band6'
;nline=3
;   band 4 

for ind=0,nline-1 do begin

if  pickband eq 'band4' and ind eq 0 then begin
filename='bb1_line.fits'
errname='bx610.bb1.cube64x64.itern.unc.fits'
basename='ci10'
smopar0=0.5
vrange=[153.069*1e6,153.522*1e6]
endif

if  pickband eq 'band4' and ind eq 0 then begin
filename='bb3_line.fits'
errname='bx610.bb3.cube64x64.itern.unc.fits'
basename='co43'
smopar0=0.5
vrange=[143.359*1e6,143.835*1e6]
endif

;   band 6

if  pickband eq 'band6' and ind eq 0 then begin
filename='bb2_line.fits'
errname='bx610.bb2.cube64x64.itern.unc.fits'
basename='co76'
smopar0=0.3
vrange=[250.964*1e6,251.448*1e6]
endif

if  pickband eq 'band6' and ind eq 1 then begin
filename='bb2_line.fits'
errname='bx610.bb2.cube64x64.itern.unc.fits'
basename='ci21'
smopar0=0.3
vrange=[251.847*1e6,252.246*1e6]
endif

if  pickband eq 'band6' and ind eq 2 then begin
filename='bb3_line.fits'
errname='bx610.bb3.cube64x64.itern.unc.fits'
basename='h2o'
smopar0=0.4
vrange=[233.918*1e6,234.379*1e6]
endif

makemom,filename,$
    errfile=errname,$
    ;maskfile=repstr(filename,'.image','.pbmask0p12'),$
    ;xyrange=[194,360,168,345],$
    baseroot='moms/'+basename,smopar=[smopar0,7800.0*0.0],$
    thresh=4.0,edge=2.0,/pvmom0,/dorms,vrange=vrange
pltmom_pv,'moms/'+basename,label={tl:basename},pratio=0.5

endfor

END