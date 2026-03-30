"use client"

import { useState, useMemo, useEffect } from "react"
import { AlertTriangle } from "lucide-react"
import { FilterBar } from "@/components/incidents/filter-bar"
import { IncidentsTable } from "@/components/incidents/incidents-table"
import { Header } from "@/components/layout/header"
import { listIncidents, type Incident } from "@/lib/api"

interface FilterState {
  search: string
  status: string
  severity: string
  service: string
  environment: string
}

const defaultFilters: FilterState = {
  search: "",
  status: "",
  severity: "",
  service: "",
  environment: "",
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<FilterState>(defaultFilters)

  useEffect(() => {
    listIncidents(100)
      .then(setIncidents)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [])

  const allServices = useMemo(
    () => [...new Set(incidents.map((i) => i.service_name).filter(Boolean))].sort() as string[],
    [incidents]
  )

  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      if (
        filters.search &&
        !inc.title.toLowerCase().includes(filters.search.toLowerCase()) &&
        !(inc.service_name ?? "").toLowerCase().includes(filters.search.toLowerCase())
      ) {
        return false
      }
      if (filters.status && inc.status?.toLowerCase() !== filters.status.toLowerCase()) return false
      if (filters.severity && inc.severity?.toLowerCase() !== filters.severity.toLowerCase()) return false
      if (filters.service && inc.service_name !== filters.service) return false
      return true
    })
  }, [incidents, filters])

  const activeCount = incidents.filter(
    (i) => !["RESOLVED", "CLOSED", "FAILED_REMEDIATION"].includes(i.status ?? "")
  ).length

  return (
    <div className="flex flex-col min-h-full">
      <Header title="Incidents" />
      <div className="flex-1 p-4 md:p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-50">Incidents</h2>
              {!loading && (
                <span className="flex items-center gap-1.5 text-xs font-semibold bg-orange-500/15 text-orange-400 border border-orange-500/20 rounded-full px-2.5 py-1">
                  <AlertTriangle className="h-3 w-3" />
                  {activeCount} active
                </span>
              )}
            </div>
            <p className="text-sm text-zinc-500 mt-1">
              Monitor and respond to active incidents across your infrastructure
            </p>
          </div>
        </div>

        <div className="mb-4">
          <FilterBar
            filters={filters}
            onFiltersChange={setFilters}
            resultCount={filteredIncidents.length}
            services={allServices}
          />
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="h-5 w-5 rounded-full border-2 border-zinc-600 border-t-blue-400 animate-spin" />
              <p className="text-xs text-zinc-500">Loading incidents…</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 text-center px-6">
              <p className="text-sm font-medium text-red-400">Failed to load incidents</p>
              <p className="text-xs text-zinc-500 mt-1 font-mono">{error}</p>
            </div>
          ) : (
            <IncidentsTable incidents={filteredIncidents} />
          )}
        </div>
      </div>
    </div>
  )
}
