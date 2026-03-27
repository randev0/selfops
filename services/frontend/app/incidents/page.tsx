"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listIncidents, type Incident } from "@/lib/api";

const statusColors: Record<string, string> = {
  OPEN: "bg-red-100 text-red-800",
  ENRICHING: "bg-yellow-100 text-yellow-800",
  ANALYZING: "bg-blue-100 text-blue-800",
  ACTION_REQUIRED: "bg-orange-100 text-orange-800",
  REMEDIATING: "bg-purple-100 text-purple-800",
  MONITORING: "bg-cyan-100 text-cyan-800",
  RESOLVED: "bg-green-100 text-green-800",
  CLOSED: "bg-gray-100 text-gray-800",
  FAILED_REMEDIATION: "bg-red-200 text-red-900",
};

const severityColors: Record<string, string> = {
  critical: "bg-red-600 text-white",
  warning: "bg-yellow-500 text-white",
  info: "bg-blue-500 text-white",
  unknown: "bg-gray-400 text-white",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      listIncidents()
        .then(setIncidents)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-bold text-gray-900">SelfOps — Incidents</h1>
      </header>
      <main className="p-6">
        {loading && <p className="text-gray-500">Loading...</p>}
        {error && <p className="text-red-600">Error: {error}</p>}
        {!loading && !error && incidents.length === 0 && (
          <p className="text-gray-500">No incidents found. System is healthy.</p>
        )}
        {incidents.length > 0 && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  {["Status", "Severity", "Title", "Service", "Namespace", "First Seen", "Age"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {incidents.map((inc) => (
                  <tr key={inc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          statusColors[inc.status] ?? "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {inc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          severityColors[inc.severity] ?? "bg-gray-400 text-white"
                        }`}
                      >
                        {inc.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/incidents/${inc.id}`}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        {inc.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {inc.service_name ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {inc.namespace ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {new Date(inc.first_seen_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {timeAgo(inc.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
