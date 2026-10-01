"""Blender 4.5 LTS: build an editable aerial accident-site reconstruction.

Run: blender --background --python build_scene.py -- --output output
All meshes and materials are procedural. No monitoring or warning devices.
The supplied aerial still informs composition, not surveyed coordinates.
"""
import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector, Matrix
from mathutils.noise import noise_vector

ROOT = Path(__file__).resolve().parent
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--output', default=str(ROOT / 'output'))
parser.add_argument('--draft', action='store_true')
parser.add_argument('--no-render', action='store_true')
args = parser.parse_args(ARGS)
OUT = Path(args.output).resolve()
OUT.mkdir(parents=True, exist_ok=True)
cfg = json.loads((ROOT / 'scene_config.json').read_text(encoding='utf-8'))
rng = random.Random(cfg['seed'])

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for col in list(bpy.data.collections):
    if col.name != 'Collection':
        bpy.data.collections.remove(col)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
scene.render.engine = 'CYCLES'
scene.cycles.samples = 16 if args.draft else cfg['render_samples']
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 5
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 2
scene.cycles.transparent_max_bounces = 4
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences
    for backend in ['OPTIX','CUDA','HIP']:
        try:
            prefs.compute_device_type=backend;prefs.get_devices()
            gpu=[d for d in prefs.devices if d.type!='CPU']
            if gpu:
                for d in prefs.devices:d.use=d.type!='CPU'
                scene.cycles.device='GPU';print('RENDER DEVICE',backend,[d.name for d in gpu],flush=True);break
        except Exception:pass
except Exception:pass
scene.render.resolution_x = 1100 if args.draft else cfg['render_width']
scene.render.resolution_y = 825 if args.draft else cfg['render_height']
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.6
scene.render.fps = 24
scene.frame_end = 240

def collection(name):
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    return col

terrain_col = collection('01_Terrain_地形')
road_col = collection('02_Road_道路护栏')
forest_col = collection('03_DenseForest_连片密林')
scar_col = collection('04_Collapse_塌方裸土')
car_col = collection('05_Vehicles_车辆示意')
camera_col = collection('06_Cameras_相机')
light_col = collection('07_Lighting_环境光')

def material(name, color, roughness=0.75, metallic=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Metallic'].default_value = metallic
    return m

def textured_material(name, low, high, scale, roughness=0.95, bump=0.15):
    m = material(name, low, roughness)
    nodes, links = m.node_tree.nodes, m.node_tree.links
    p = nodes.get('Principled BSDF')
    tex = nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = scale
    tex.inputs['Detail'].default_value = 5
    tex.inputs['Roughness'].default_value = .75
    coords = nodes.new('ShaderNodeTexCoord')
    links.new(coords.outputs['Object'], tex.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .22
    ramp.color_ramp.elements[0].color = (*low, 1)
    ramp.color_ramp.elements[1].position = .78
    ramp.color_ramp.elements[1].color = (*high, 1)
    links.new(tex.outputs['Fac'], ramp.inputs[0])
    links.new(ramp.outputs['Color'], p.inputs['Base Color'])
    b = nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = bump
    b.inputs['Distance'].default_value = .12
    links.new(tex.outputs['Fac'], b.inputs['Height'])
    links.new(b.outputs['Normal'], p.inputs['Normal'])
    return m

soil = textured_material('Exposed ochre earth / 裸露黄褐土',(.20,.105,.042),(.58,.36,.17),1.5,bump=.35)
forest_floor = textured_material('Forest understory / 林下地表',(.028,.055,.020),(.13,.19,.067),.55,bump=.2)
asphalt = textured_material('Wet weathered asphalt / 潮湿沥青',(.045,.055,.061),(.10,.12,.12),13,.68,.14)
cut_asphalt = textured_material('Broken asphalt aggregate / 沥青断面',(.055,.059,.055),(.23,.22,.19),9,bump=.3)
white = material('Weathered road paint / 旧白色标线',(.72,.74,.66),.8)
metal = material('Galvanized guardrail / 镀锌护栏',(.37,.42,.41),.4,.68)
concrete = textured_material('Concrete drainage / 混凝土排水',(.28,.30,.26),(.48,.49,.41),3,bump=.12)
bark = textured_material('Tree bark / 树皮',(.06,.039,.019),(.20,.15,.078),4,bump=.22)
leaf_mats=[]
for i, (lo,hi) in enumerate([
 ((.022,.065,.024),(.115,.25,.075)),((.035,.083,.021),(.18,.29,.074)),
 ((.035,.087,.042),(.15,.285,.12)),((.062,.115,.027),(.26,.36,.105)),
 ((.022,.065,.035),(.10,.215,.11)),((.04,.10,.048),(.21,.34,.17))]):
    m=textured_material('Broadleaf canopy %02d / 阔叶树冠'%i,lo,hi,6,.9,.20)
    m.node_tree.nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value=.045
    leaf_mats.append(m)

def mesh_obj(name, vertices, faces, mats, col, indices=None, smooth=False):
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.clear()
    for m in mats: mesh.materials.append(m)
    mesh.update()
    if indices:
        for p,mi in zip(mesh.polygons,indices): p.material_index=mi
    if smooth:
        for p in mesh.polygons:p.use_smooth=True
    ob=bpy.data.objects.new(name,mesh)
    col.objects.link(ob)
    return ob

def cx(y): return .0011*y*y + .085*y
def road_h(y): return 35 + .004*y + .6*math.sin(y/100)
def local_x(x,y): return x-cx(y)
def scar_width(z):
    return 0 if z<.9 or z>88 else 12 + 15*math.sin((z-1)/87*math.pi) + 4*math.sin(z*.2)
def is_scar(z,y,extra=0):
    return z>1 and z<88+extra and abs(y+0.35*(z-12)) < scar_width(min(z,87))+extra
def terrain_h(z,y,collapsed=True):
    h=road_h(y)
    if z < -13:
        d=-z-13
        h+= min(75,d*.45)+math.sin(y/65)*min(d*.08,5)+math.sin(d/25)*3
    elif z>13:
        d=z-13
        valley=math.exp(-((y+10)/100)**2)
        h-= min(33,d*.52)
        h+= max(0,z-83)*.31 + (1-valley)*8*math.sin(min(1,d/100)*math.pi)
        h+=math.sin(y/44)*min(d*.06,2)
    else: h-=.24
    if collapsed and is_scar(z,y):
        f=max(0,1-(abs(y+.35*(z-12))/max(1,scar_width(z)))**2)
        h-=f*(7 if z<13 else 3.5*math.sin((z-1)/87*math.pi))
    return h

def surface_world(z,y,up=0): return (cx(y)+z,y,terrain_h(z,y)+up)

print('BUILD terrain',flush=True)
verts=[];faces=[];mi=[]
ys=[-280+i*2 for i in range(311)]
zs=[-200+i*2 for i in range(201)]
for y in ys:
    for z in zs:
        h=terrain_h(z,y)
        if abs(z)>14:h+=.22*math.sin(z*1.3+y*.7)*math.sin(y*.6)
        verts.append((cx(y)+z,y,h))
nz=len(zs)
for i in range(len(ys)-1):
    for j in range(nz-1):
        a=i*nz+j;faces.append((a,a+1,a+nz+1,a+nz))
        mi.append(1 if is_scar(zs[j]+1,ys[i]+1) else 0)
mesh_obj('Ground_surface_林地与滑塌土坡',verts,faces,[forest_floor,soil],terrain_col,mi,True)

def ribbon(name,y0,y1,z0,z1,mat,up=.03,grounded=False,col=road_col,step=2):
    vs=[];fs=[];n=max(1,math.ceil((y1-y0)/step))
    for i in range(n+1):
        y=y0+(y1-y0)*i/n
        for z in [z0,z1]:vs.append((cx(y)+z,y,(terrain_h(z,y) if grounded else road_h(y))+up))
    for i in range(n):a=i*2;fs.append((a,a+1,a+3,a+2))
    return mesh_obj(name,vs,fs,[mat],col)

def tube(name, points, radius, mat, col=road_col, resolution=2):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=1
    spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
    for p,co in zip(spline.points,points):p.co=(*co,1)
    curve.bevel_depth=radius;curve.bevel_resolution=resolution
    ob=bpy.data.objects.new(name,curve);col.objects.link(ob);curve.materials.append(mat);return ob

def box(name, center, scale, mat, col=road_col, rot=0):
    vs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    fs=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    ob=mesh_obj(name,vs,fs,[mat],col);ob.location=center;ob.scale=tuple(v/2 for v in scale);ob.rotation_euler.z=rot;return ob

print('BUILD road',flush=True)
ribbon('West_carriageway_完整半幅',-280,340,-12,-1,asphalt)
ribbon('East_carriageway_before_gap',-280,-11,1,12,asphalt)
ribbon('East_carriageway_after_gap',11,340,1,12,asphalt)
ribbon('Central_median_中央分隔带',-280,340,-1,1,forest_floor,.08)
for z in [-10.6,-2.1,2.1,10.6]:
    spans=[(-280,340)] if z<0 else [(-280,-11),(11,340)]
    for a,b in spans:ribbon('Edge_marking_车道边线',a,b,z-.08,z+.08,white,.045)
for z in [-6.3,6.3]:
    for y in range(-278,337,15):
        if z>0 and -18<y<14:continue
        ribbon('Dashed_lane_line_虚线',y,y+6,z-.075,z+.075,white,.05)

# Irregular fractured pavement lips; avoid the misleading rectangular excavated pit.
for end in [-1,1]:
    vs=[]
    for i in range(17):
        z=1+i*11/16;y=end*(9.5+rng.uniform(-1.7,1.3));h=road_h(y)
        vs.extend([(cx(y)+z,y,h+.03),(cx(y)+z,y,h-.7)])
    fs=[(i*2,i*2+2,i*2+3,i*2+1) for i in range(16)]
    mesh_obj('Fractured_asphalt_edge_不规则沥青断口',vs,fs,[cut_asphalt],scar_col)
    top=[(cx(end*14)+1,end*14,road_h(end*14))]+[vs[i] for i in range(0,len(vs),2)]+[(cx(end*14)+12,end*14,road_h(end*14))]
    mesh_obj('Asphalt_lip_残留路面',top,[tuple(range(len(top)))],[asphalt],scar_col)

for z in [-12,-1.15,1.15,12]:
    spans=[(-280,340)] if z<0 else [(-280,-12),(12,340)]
    for a,b in spans:
        for height in [.65,.95]:
            tube('W_guardrail_波形护栏',[(cx(y)+z,y,road_h(y)+height) for y in range(a,b+1,3)],.075,metal)
        for y in range(a,b,5):box('Guardrail_post_立柱',(cx(y)+z,y,road_h(y)+.46),(.1,.12,.95),metal)
# Sagging broken guardrail across the missing half width.
for z in [1.15,12]:
    pts=[]
    for i in range(25):
        y=-12+i
        pts.append((cx(y)+z+1.8*math.sin(i/24*math.pi),y,road_h(y)+.75-3.5*math.sin(i/24*math.pi)))
    tube('Bent_guardrail_变形护栏',pts,.08,metal,scar_col)

# Small real-world drainage geometry, not measurement equipment.
for z in [-13.5,13.5]:
    for a,b in [(-280,-35),(38,340)]:
        tube('Roadside_drain_路侧排水沟',[surface_world(z,y,.08) for y in range(a,b,3)],.23,concrete)
for y in [58,86,116]:
    pts=[surface_world(z,y,.16) for z in range(15,69)]
    tube('Slope_drain_边坡排水槽',pts,.42,concrete)
for z in [31,50,67]:
    tube('Slope_berm_drain_平台排水线',[surface_world(z,y,.1) for y in range(48,133,2)],.25,concrete)

print('BUILD debris',flush=True)
for i in range(88):
    z=rng.uniform(5,79);y=-.35*(z-12)+rng.uniform(-1,1)*scar_width(z)*.8
    size=rng.uniform(.35,1.7)*(1.2 if z<30 else .65)
    verts=[(math.cos(a*math.pi/3)*size,math.sin(a*math.pi/3)*size,0) for a in range(6)]
    verts += [(x*.82,y*.82,rng.uniform(.18,.5)) for x,y,_ in verts]
    faces=[tuple(range(5,-1,-1)),tuple(range(6,12))]+[(j,(j+1)%6,(j+1)%6+6,j+6) for j in range(6)]
    ob=mesh_obj('Debris_%03d'%i,verts,faces,[cut_asphalt if i%3==0 else soil],scar_col)
    ob.location=surface_world(z,y,.2);ob.rotation_euler=(rng.uniform(-.6,.6),rng.uniform(-.5,.5),rng.random()*6.28)

# Canopy prototypes combine many irregular small leaf masses and protruding leaf sprays.
# Thousands of shared-mesh instances form a closed, varied broadleaf canopy.
print('BUILD dense broadleaf forest',flush=True)
def crown_mesh(index):
    r=random.Random(700+index);vs=[];fs=[];mis=[]
    leaf_color=index%len(leaf_mats)
    height=r.uniform(7.5,12)
    for k in range(100):
        a=r.random()*math.tau;rad=math.sqrt(r.random())*3.6
        px=math.cos(a)*rad;py=math.sin(a)*rad
        pz=height-1.8*(rad/3.6)**2+r.uniform(-1.4,1.1)
        sx=r.uniform(.55,1.3);sy=r.uniform(.55,1.25);sz=r.uniform(.55,1.2)
        base=len(vs);rings=5;segs=7
        for j in range(rings+1):
            lat=math.pi*j/rings
            for q in range(segs):
                lon=math.tau*q/segs;dist=1+r.uniform(-.22,.22)
                vs.append((px+math.sin(lat)*math.cos(lon)*sx*dist,py+math.sin(lat)*math.sin(lon)*sy*dist,pz+math.cos(lat)*sz*dist))
        for j in range(rings):
            for q in range(segs):
                v=base+j*segs+q;vn=base+j*segs+(q+1)%segs
                fs.append((v,vn,vn+segs,v+segs));mis.append((leaf_color+(1 if r.random()<.14 else 0))%len(leaf_mats))
    for k in range(240):
        a=r.random()*math.tau;rad=math.sqrt(r.random())*4.1
        x=math.cos(a)*rad;y=math.sin(a)*rad;z=height-1.8*(rad/4)**2+r.uniform(-.5,1.4)
        a=r.random()*math.tau;l=r.uniform(.18,.4);base=len(vs)
        vs.extend([(x-l*math.cos(a),y-l*math.sin(a),z),(x+.15*math.sin(a),y-.15*math.cos(a),z+.12),(x+l*math.cos(a),y+l*math.sin(a),z+.03),(x-.15*math.sin(a),y+.15*math.cos(a),z+.1)])
        fs.append((base,base+1,base+2,base+3));mis.append(leaf_color)
    mesh=bpy.data.meshes.new('Canopy_shared_%02d'%index);mesh.from_pydata(vs,[],fs)
    for m in leaf_mats:mesh.materials.append(m)
    for p,i in zip(mesh.polygons,mis):p.material_index=i;p.use_smooth=True
    mesh.update();return mesh,height

prototypes=[crown_mesh(i) for i in range(12)]
# A shared tapered trunk mesh with a few forks visible at forest margins.
tv=[];tf=[]
for z,rad in [(0,.24),(5,.13),(8,.055)]:
    for j in range(7):tv.append((math.cos(j*math.tau/7)*rad,math.sin(j*math.tau/7)*rad,z))
for k in range(2):
    for j in range(7):a=k*7+j;b=k*7+(j+1)%7;tf.append((a,b,b+7,a+7))
trunk_mesh=bpy.data.meshes.new('Trunk_shared');trunk_mesh.from_pydata(tv,[],tf);trunk_mesh.materials.append(bark)
count=0;spacing=cfg['forest_spacing_m']
for row in range(int(610/spacing)):
    y=-275+row*spacing+rng.uniform(-2,2)
    for column in range(int(390/spacing)):
        z=-195+column*spacing+rng.uniform(-2,2)
        if -18<z<18:continue
        if is_scar(z,y,6):continue
        if 14<z<72 and 46<y<135:
            if any(abs(y-d)<3 for d in [58,86,116]):continue
        if rng.random()<.035:continue
        mesh,height=rng.choice(prototypes)
        ob=bpy.data.objects.new('Tree_%05d'%count,mesh);forest_col.objects.link(ob)
        ob.location=surface_world(z,y,-.1);s=rng.uniform(.72,1.17)
        if 15<z<74 and 43<y<137:s*=.45
        ob.scale=(s*rng.uniform(.85,1.14),s*rng.uniform(.85,1.12),s*rng.uniform(.85,1.15))
        ob.rotation_euler.z=rng.random()*math.tau
        if abs(z)<38 or is_scar(z,y,16):
            trunk=bpy.data.objects.new('Trunk_%05d'%count,trunk_mesh);forest_col.objects.link(trunk)
            trunk.location=ob.location;trunk.scale=ob.scale
        count+=1
print('Forest trees:',count,flush=True)

# Small road vehicles establish scale without claiming exact accident positions/counts.
body_mats=[material('Car paint '+str(i),c,.3,.25) for i,c in enumerate([(.65,.69,.66),(.06,.12,.18),(.68,.68,.61),(.04,.24,.27)])]
glass=material('Dark vehicle glass',(.025,.065,.08),.18,.4)
tire=material('Rubber',(.012,.015,.015),.85)
def car(y,z,index):
    base=Vector((cx(y)+z,y,road_h(y)+.03));rot=-math.atan(.0022*y+.085)
    color=body_mats[index%len(body_mats)]
    ob=box('Vehicle_%02d_body'%index,base+Vector((0,0,.65)),(1.85,4.4,1.1),color,car_col,rot)
    bevel=ob.modifiers.new('Soft body edges','BEVEL');bevel.width=.12;bevel.segments=2
    roof=box('Vehicle_%02d_cabin'%index,base+Vector((0,-.1,1.43)),(1.55,2.45,.74),glass,car_col,rot)
    bevel=roof.modifiers.new('Cabin edges','BEVEL');bevel.width=.14;bevel.segments=2
    for dy in [-1.35,1.35]:
        for dx in [-.89,.89]:box('Vehicle_wheel',base+Vector((dx,dy,.36)),(.25,.65,.65),tire,car_col,rot)
for i,(y,z) in enumerate([(-88,-4.1),(-132,-8.1),(64,-4.1),(93,-8.1),(135,-4.1),(163,-8.1),(205,-4.1),(227,-8.1)]):car(y,z,i)

print('BUILD cameras and daylight',flush=True)
world=bpy.data.worlds.new('Overcast daylight / 阴天环境');world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.64,.73,.81,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.55
scene.world=world
sun_data=bpy.data.lights.new('Soft sun','SUN');sun_data.energy=1.7;sun_data.angle=math.radians(22)
sun=bpy.data.objects.new('Soft sun',sun_data);light_col.objects.link(sun);sun.rotation_euler=(math.radians(24),math.radians(-18),math.radians(-35))
area_data=bpy.data.lights.new('Large sky fill','AREA');area_data.energy=12000;area_data.shape='DISK';area_data.size=180
area=bpy.data.objects.new('Large sky fill',area_data);light_col.objects.link(area);area.location=(-60,40,190)

def camera(name,location,target,lens):
    data=bpy.data.cameras.new(name);data.lens=lens;data.clip_end=2000
    ob=bpy.data.objects.new(name,data);camera_col.objects.link(ob);ob.location=location
    ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    return ob
overview=camera('01_Aerial_reference_航拍主视角',(105,-210,285),(24,47,20),42)
detail=camera('02_Collapse_detail_塌方近景',(77,-88,89),(12,-3,20),45)
driver=camera('03_Road_level_道路视角',(cx(-74)+6,-74,road_h(-74)+1.7),(cx(12)+6,12,road_h(12)-.5),32)
scene.camera=overview
scene['source_note']='Approximate reconstruction from user supplied aerial still. No surveyed geometry. Daytime aftermath, not proven moment-of-collapse geometry.'
scene['scope']='Road, dense forest, slope, damaged pavement and debris only. No monitoring devices or warning systems.'
scene['tree_count']=count
scene['units']='metres, local scene coordinates'

# Optional night/rain/fog collections are visual alternatives, disabled for the photo-match view.
weather_col=collection('08_OptionalAtmosphere_可选雨雾_默认关闭')
fog_mat=bpy.data.materials.new('Optional mist');fog_mat.use_nodes=True
nodes=fog_mat.node_tree.nodes;nodes.clear();output=nodes.new('ShaderNodeOutputMaterial');vol=nodes.new('ShaderNodeVolumePrincipled');vol.inputs['Density'].default_value=.004;vol.inputs['Color'].default_value=(.68,.74,.75,1);fog_mat.node_tree.links.new(vol.outputs['Volume'],output.inputs['Volume'])
fog=box('Optional mist volume / 雾为可选效果', (20,20,65),(850,850,140),fog_mat,weather_col)
fog.hide_render=True;fog.hide_viewport=True
fog['note']='Optional visual atmosphere only; fog is not asserted as recorded accident weather.'

text=bpy.data.texts.new('READ_ME_场景说明')
text.write('梅大高速事故现场：基于用户航拍参考的近似场景重建。\n主场景为白天灾后状态。道路尺寸、车辆位置和植被均为示意，未进行测绘配准。\n集合按地形、道路、密林、塌方、车辆、相机分类。没有边坡监测、预警、风险评分或数据面板。\n01_Aerial_reference 为主相机；02_Collapse_detail 为塌方近景。\n可选雾体默认关闭，不作为事故当晚气象事实。\n')
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL'
            area.spaces.active.overlay.show_overlays=False
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'meida_accident_scene.blend'),compress=True)
manifest={'blender':bpy.app.version_string,'trees':count,'objects':len(scene.objects),'shared_canopy_meshes':len(prototypes),'scene':'daytime aftermath approximation','config':cfg}
(OUT/'scene_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
if not args.no_render:
    for cam,name in [(overview,'aerial_overview'),(detail,'collapse_detail')]:
        scene.camera=cam;scene.render.filepath=str(OUT/(name+'.png'))
        print('RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
    scene.camera=overview
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'meida_accident_scene.blend'),compress=True)
print('DONE',OUT,flush=True)
