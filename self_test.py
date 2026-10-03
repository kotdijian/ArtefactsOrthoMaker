"""Geometry/file-format self test for ArtefactsOrthoMaker v1.0.0."""
from __future__ import annotations
import math, tempfile
from pathlib import Path
import numpy as np, trimesh
from pose_core import estimate_slice_axis, export_normalized_mesh, load_mesh_asset, rotation_from_a_to_b

def synthetic_vessel(height=120.,radius_bottom=35.,radius_top=55.,radial=180,levels=80):
    z=np.linspace(0.,height,levels); th=np.linspace(0.,2*np.pi,radial,endpoint=False)
    zz,tt=np.meshgrid(z,th,indexing="ij"); r=radius_bottom+(radius_top-radius_bottom)*(zz/max(height,1e-9)); r*=1.+0.025*np.cos(3*tt)
    v=np.column_stack([(r*np.cos(tt)).ravel(),(r*np.sin(tt)).ravel(),zz.ravel()]); f=[]
    for i in range(levels-1):
        for j in range(radial):
            a=i*radial+j; b=i*radial+(j+1)%radial; c=(i+1)*radial+j; d=(i+1)*radial+(j+1)%radial
            f += [[a,c,b],[b,c,d]]
    return trimesh.Trimesh(vertices=v,faces=np.asarray(f),process=False)

def main():
    target=np.array([.31,-.42,.853]); target/=np.linalg.norm(target)
    r=rotation_from_a_to_b(np.array([0.,0.,1.]),target)
    mesh=synthetic_vessel(height=150); mesh.vertices=mesh.vertices@r.T+np.array([120.,-80.,30.])
    est=estimate_slice_axis(mesh.vertices); dot=abs(float(np.dot(est.direction,target))); angle=math.degrees(math.acos(np.clip(dot,-1,1)))
    print(f"axis error={angle:.3f} deg"); assert angle<12.
    with tempfile.TemporaryDirectory() as td:
        p=Path(td); src=p/"sample.ply"; dst=p/"sample_rev.ply"
        src.write_bytes(trimesh.exchange.ply.export_ply(mesh,encoding="binary",vertex_normal=False))
        asset=load_mesh_asset(src,"mm"); export_normalized_mesh(asset,np.eye(4),dst); assert dst.exists()
    print("SELF TEST PASSED")

if __name__=="__main__": main()
