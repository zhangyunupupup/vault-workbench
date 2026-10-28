import {indexSTL} from './layout-mesh-codec.js';
self.onmessage=event=>{
  try{const result=indexSTL(event.data.buffer,event.data.supports);self.postMessage(result,[result.positions.buffer,result.index.buffer]);}
  catch(e){self.postMessage({error:e.message});}
};
