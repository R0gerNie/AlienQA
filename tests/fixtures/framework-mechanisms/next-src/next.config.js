const path=require('path');
// Include both project and the reused T02 dependencies in Turbopack's boundary.
module.exports={devIndicators:false,turbopack:{root:path.resolve(__dirname,'../../../../..')}};
