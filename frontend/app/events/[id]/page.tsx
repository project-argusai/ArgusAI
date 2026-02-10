/**
 * Individual event page - redirects to events list with the event selected
 * 
 * This route exists to handle direct links to /events/{id} (e.g., from PackageDeliveryWidget).
 * It redirects to the main events page with a query param to open the event detail modal.
 */

import { redirect } from 'next/navigation';

interface EventPageProps {
  params: Promise<{ id: string }>;
}

export default async function EventPage({ params }: EventPageProps) {
  const { id } = await params;
  // Redirect to events page with selected event
  redirect(`/events?selected=${id}`);
}
