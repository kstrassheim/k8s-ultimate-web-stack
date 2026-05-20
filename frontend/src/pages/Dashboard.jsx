import { isNewDashboardEnabled } from '@/config';
import WorldlineMonitor from '@/pages/components/WorldlineMonitor';
import { Alert } from 'react-bootstrap';

/**
 * Dashboard page - gated by NEW_DASHBOARD feature flag
 * When enabled: shows the new WorldlineMonitor dashboard UI
 * When disabled: shows a "dashboard unavailable" message
 */
const Dashboard = () => {
  if (!isNewDashboardEnabled) {
    return (
      <div data-testid="dashboard-page">
        <Alert variant="info" data-testid="dashboard-unavailable">
          <Alert.Heading>Dashboard Unavailable</Alert.Heading>
          <p>The new dashboard is not currently enabled. Check back soon!</p>
        </Alert>
      </div>
    );
  }

  return (
    <div data-testid="dashboard-page">
      <WorldlineMonitor />
    </div>
  );
};

export default Dashboard;
