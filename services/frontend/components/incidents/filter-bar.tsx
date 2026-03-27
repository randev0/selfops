"use client"

import { Search, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface FilterState {
  search: string
  status: string
  severity: string
  service: string
  environment: string
}

interface FilterBarProps {
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  resultCount: number
  services: string[]
}

const statuses = [
  "open",
  "enriching",
  "analyzing",
  "action_required",
  "remediating",
  "monitoring",
  "resolved",
  "failed_remediation",
]

const severities = ["critical", "high", "medium", "low"]

function SelectFilter({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  options: string[]
  placeholder: string
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 appearance-none bg-zinc-900 border border-zinc-800 rounded-lg pl-3 pr-7 text-xs text-zinc-400 focus:outline-none focus:border-zinc-700 cursor-pointer hover:bg-zinc-800/70 transition-colors"
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-zinc-600 pointer-events-none" />
    </div>
  )
}

export function FilterBar({ filters, onFiltersChange, resultCount, services }: FilterBarProps) {
  const update = (patch: Partial<FilterState>) =>
    onFiltersChange({ ...filters, ...patch })

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-600 pointer-events-none" />
        <input
          type="text"
          placeholder="Search incidents..."
          value={filters.search}
          onChange={(e) => update({ search: e.target.value })}
          className="h-8 w-56 bg-zinc-900 border border-zinc-800 rounded-lg pl-8 pr-3 text-xs text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 focus:ring-1 focus:ring-zinc-700 transition-colors"
        />
      </div>

      {/* Status */}
      <SelectFilter
        value={filters.status}
        onChange={(v) => update({ status: v })}
        options={statuses}
        placeholder="All Statuses"
      />

      {/* Severity */}
      <SelectFilter
        value={filters.severity}
        onChange={(v) => update({ severity: v })}
        options={severities}
        placeholder="All Severities"
      />

      {/* Service */}
      <SelectFilter
        value={filters.service}
        onChange={(v) => update({ service: v })}
        options={services}
        placeholder="All Services"
      />

      {/* Environment toggle */}
      <div className="flex h-8 rounded-lg border border-zinc-800 overflow-hidden">
        {(["", "production", "staging"] as const).map((e) => (
          <button
            key={e}
            onClick={() => update({ environment: e })}
            className={cn(
              "px-3 text-xs font-medium transition-colors",
              filters.environment === e
                ? "bg-zinc-700 text-zinc-100"
                : "bg-zinc-900 text-zinc-500 hover:bg-zinc-800/70"
            )}
          >
            {e === "" ? "All" : e === "production" ? "Prod" : "Staging"}
          </button>
        ))}
      </div>

      {/* Result count */}
      <span className="ml-auto text-xs text-zinc-500">
        <span className="font-semibold text-zinc-300">{resultCount}</span> incident
        {resultCount !== 1 ? "s" : ""}
      </span>
    </div>
  )
}
