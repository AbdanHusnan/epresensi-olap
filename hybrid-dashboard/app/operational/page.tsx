import { requireRole } from '../../lib/auth';
import { DashboardPage } from '../../components/dashboard-page';
export const dynamic = 'force-dynamic';
export default async function OperationalPage() { return <DashboardPage user={await requireRole('manager')}/>; }
