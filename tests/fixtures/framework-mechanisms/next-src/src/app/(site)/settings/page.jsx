import Link from 'next/link';
import Form from '../../form';
export default function Settings(){return <main><h1>Grouped settings</h1><Form/><Link href="/users/7?tab=2#profile">User seven</Link><Link href="/records/7?tab=2#profile">Record seven</Link></main>}
