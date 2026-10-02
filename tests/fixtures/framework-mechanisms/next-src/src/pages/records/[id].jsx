import Details from '../../app/details/page';
export default function Record({id}){return <main><h1>Record {id}</h1><Details/></main>}
export function getServerSideProps({params}){return {props:{id:params.id}}}
