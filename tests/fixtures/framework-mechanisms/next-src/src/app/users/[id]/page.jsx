import Details from '../../details/page';
export default async function User({params}){const {id}=await params;return <main><h1>User {id}</h1><Details/></main>}
