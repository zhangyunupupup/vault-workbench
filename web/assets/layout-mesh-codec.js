// Lossless position indexing: retain every source triangle and vertex coordinate.
// Flat shading derives the face normal, so sharing positions never rounds edges.
export function indexSTL(buffer,supports){
  if(buffer.byteLength<134)throw Error('模型文件不完整。');
  const view=new DataView(buffer),faces=view.getUint32(80,true);
  if(!faces||faces>3200000||buffer.byteLength!==84+faces*50)throw Error('模型格式或大小超出预览范围。');
  const index=new Uint32Array(faces*3),vertices=new Map(),lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
  for(let f=0;f<faces;f++)for(let v=0;v<3;v++)for(let a=0;a<3;a++){
    const n=view.getFloat32(96+f*50+v*12+a*4,true);
    if(!Number.isFinite(n))throw Error('模型包含无效坐标。');lo[a]=Math.min(lo[a],n);hi[a]=Math.max(hi[a],n);
  }
  const cx=(lo[0]+hi[0])/2,cy=(lo[1]+hi[1])/2;
  let points=new Float32Array(Math.min(faces*3,262144)*3),count=0,kept=0;
  for(let f=0;f<faces;f++){
    if(supports?.remove_boxes.some(b=>[0,1,2].every(v=>{
      const at=96+f*50+v*12,p=[Math.fround(view.getFloat32(at,true)-cx),Math.fround(view.getFloat32(at+8,true)-lo[2]),Math.fround(cy-view.getFloat32(at+4,true))];
      return p.every((n,a)=>n>=b.min[a]&&n<=b.max[a]);
    })))continue;
    for(let v=0;v<3;v++){
    const at=84+f*50+12+v*12,x=view.getFloat32(at,true),y=view.getFloat32(at+4,true),z=view.getFloat32(at+8,true);
    if(!Number.isFinite(x)||!Number.isFinite(y)||!Number.isFinite(z))throw Error('模型包含无效坐标。');
    const key=`${x},${y},${z}`;let id=vertices.get(key);
    if(id===undefined){
      id=count++;vertices.set(key,id);
      if(count*3>points.length){const grown=new Float32Array(Math.min(faces*9,points.length*2));grown.set(points);points=grown;}
      points.set([x,y,z],id*3);
    }
    index[kept*3+v]=id;
    }
    kept++;
  }
  if(supports&&faces-kept!==supports.removed_faces)throw Error('辅助支撑区域与已核对版本不一致。');
  const positions=points.slice(0,count*3);
  for(let i=0;i<positions.length;i+=3){const y=positions[i+1];positions[i]-=cx;positions[i+1]=positions[i+2]-lo[2];positions[i+2]=cy-y;}
  return {positions,index:index.slice(0,kept*3),faces,removed_faces:faces-kept};
}
