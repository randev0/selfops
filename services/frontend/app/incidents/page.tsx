"use client"

import { useState, useMemo } from "react"
import { AlertTriangle } from "lucide-react"
import { FilterBar } from "@/components/incidents/filter-bar"
import { IncidentsTable } from "@/components/incidents/incidents-table"
import { Header } from "@/components/layout/header"
import { mockIncidents } from "@/lib/mock-data"

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

const allServices = [...new Set(mockIncidents.map((i) => i.service))].sort()

export default function IncidentsPage() {
  const [filters, setFilters] = useState<FilterState>(defaultFilters)

  const filteredIncidents = useMemo(() => {
    return mockIncidents.filter((inc) => {
      if (
        filters.search &&
        !inc.title.toLowerCase().includes(filters.search.toLowerCase()) &&
        !inc.service.toLowerCase().includes(filters.search.toLowerCase())
      ) {
        return false
      }
      if (filters.status && inc.status !== filters.status) return false
      if (filters.severity && inc.severity !== filters.severity) return false
      if (filters.service && inc.service !== filters.service) return false
      if (filters.environment && inc.environment !== filters.environment) return false
      return true
    })
  }, [filters])

  const activeCount = mockIncidents.filter(
    (i) => i.status !== "resolved" && i.status !== "failed_remediation"
  ).length

  return (
    <div className="flex flex-col min-h-full">
      <Header title="Incidents" />
      <div className="flex-1 p-6">
        {/* Page header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-50">Incidents</h2>
              <span className="flex items-center gap-1.5 text-xs font-semibold bg-orange-500/15 text-orange-400 border border-orange-500/20 rounded-full px-2.5 py-1">
                <AlertTriangle className="h-3 w-3" />
                {activeCount} active
              </span>
            </div>
            <p className="text-sm text-zinc-500 mt-1">
              Monitor and respond to active incidents across your infrastructure
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="mb-4">
          <FilterBar
            filters={filters}
            onFiltersChange={setFilters}
            resultCount={filteredIncidents.length}
            services={allServices}
          />
        </div>

        {/* Table */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <IncidentsTable incidents={filteredIncidents} />
        </div>
      </div>
    </div>
  )
}
