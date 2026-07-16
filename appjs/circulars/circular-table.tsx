/* eslint-disable react/jsx-no-comment-textnodes */
/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2024
 * Contact http://www.logilab.fr -- mailto:contact@logilab.fr
 *
 * This software is governed by the CeCILL-C license under French law and
 * abiding by the rules of distribution of free software. You can use,
 * modify and/ or redistribute the software under the terms of the CeCILL-C
 * license as circulated by CEA, CNRS and INRIA at the following URL
 * "http://www.cecill.info
 *
 * As a counterpart to the access to the source code and rights to copy,
 * modify and redistribute granted by the license, users are provided only
 * with a limited warranty and the software's author, the holder of the
 * economic rights, and the successive licensors have only limited liability.
 *
 * In this respect, the user's attention is drawn to the risks associated
 * with loading, using, modifying and/or developing or reproducing the
 * software by the user in light of its specific status of free software,
 * that may mean that it is complicated to manipulate, and that also
 * therefore means that it is reserved for developers and experienced
 * professionals having in-depth computer knowledge. Users are therefore
 * encouraged to load and test the software's suitability as regards their
 * requirements in conditions enabling the security of their systemsand/or
 * data to be ensured and, more generally, to use and operate it in the
 * same conditions as regards security.
 *
 * The fact that you are presently reading this means that you have had
 * knowledge of the CeCILL-C license and that you accept its terms.
 */

// Adapted from
// tanstack-table-example-filters
//

import React from 'react'

import {
    Table,
    Column,
    useReactTable,
    SortingState,
    ColumnFiltersState,
    getCoreRowModel,
    getFilteredRowModel,
    getFacetedUniqueValues,
    getFacetedMinMaxValues,
    getPaginationRowModel,
    getSortedRowModel,
    ColumnDef,
    flexRender,
} from '@tanstack/react-table'

import {translate as t} from '../translate'
import {DebouncedInput} from './debouncedInput'
import {DebouncedSelect} from './debouncedSelect'

import {allFilter} from './filters'

import './index.css'

export interface ICircular {
    eid: number
    code: string
    date?: string
    title: string
    url: string
    status: string
    status_orig: string
    business: string[]
}

export interface ICircularTable {
    locale: string | undefined
}

export function CircularTable({locale}: ICircularTable) {
    const [data, setData] = React.useState<ICircular[] | []>([])
    const [loading, setLoading] = React.useState(true)
    const [globalFilter, setGlobalFilter] = React.useState('')
    const [columnFilters, setColumnFilters] =
        React.useState<ColumnFiltersState>([])
    const [sorting, setSorting] = React.useState<SortingState>([
        {id: 'date', desc: true},
    ])
    React.useEffect(() => {
        fetch('/circulars-tb-data.json', {credentials: 'same-origin'})
            .then((response) => response.json())
            .then((data) => {
                setData(data)
                setLoading(false)
            })
            .catch((error) => {
                console.error(error)
            })
    }, [])
    const columns = React.useMemo<ColumnDef<ICircular>[]>(
        () => [
            {
                header: t('Code'),
                accessorKey: 'code',
                cell: (info) => info.getValue(),
            },
            {
                header: t('Date'),
                id: 'date',
                accessorKey: 'date',
                cell: (info) => {
                    const date = info.row.original.date
                    if (date) {
                        return new Date(date).toLocaleDateString(locale)
                    }
                },
            },
            {
                header: t('Title'),
                id: 'link',
                accessorKey: 'title',
                cell: (info) => {
                    const value = info.row.original
                    return <a href={value.url}>{value.title}</a>
                },
            },
            {
                header: t('Status'),
                accessorKey: 'status',
                id: 'status',
                cell: (info) => {
                    const value = info.row.original
                    return (
                        <p className="circular-status-wrap">
                            <span
                                className={`circular-status circular-status-${value.status_orig} fr-mr-1w`}
                            ></span>
                            {value.status}
                        </p>
                    )
                },
            },
            {
                header: t('Business field'),
                id: 'business',
                //accessorKey: 'business',
                accessorFn: (row) => {
                    const values = row['business']
                    if (values) {
                        return values.join(', ')
                    }
                },
            },
        ],
        [],
    )

    const table = useReactTable<ICircular>({
        data,
        columns,
        state: {
            sorting,
            columnFilters,
            globalFilter,
            columnVisibility: {},
            // keep title column for GlobalFilter search as it doesn't work on
            // <td> child HTML elements (formatted data)
        },
        initialState: {
            pagination: {
                pageSize: 20,
            },
        },
        onGlobalFilterChange: setGlobalFilter,
        globalFilterFn: allFilter,
        onColumnFiltersChange: setColumnFilters,
        onSortingChange: setSorting,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getFacetedUniqueValues: getFacetedUniqueValues(),
        getFacetedMinMaxValues: getFacetedMinMaxValues(),
        debugTable: false,
        debugHeaders: false,
        debugColumns: false,
    })
    if (loading) {
        return <h1>{t('Loading')}</h1>
    }

    const tableSize = table.getPrePaginationRowModel().rows.length

    var tableSizeLabel = t('lines')
    var circularSizeLabel = t('Circulars')

    if (tableSize < 2) {
        tableSizeLabel = t('line')
        circularSizeLabel = t('Circular')
    }
    const businessColumn = table.getColumn('business')
    if (businessColumn === undefined) {
        return <p>Error while fetching 'business' column</p>
    }

    return (
        <div className="fr-hidden fr-unhidden-md">
            <div className="fr-table fr-table--bordered fr-table--no-scroll">
                <div className="fr-table__header">
                    <div>
                        {tableSize} {circularSizeLabel}
                    </div>
                    <div>
                        <label className="fr-label" htmlFor="table-all-search">
                            {t('Search all columns...')}
                        </label>
                        <DebouncedInput
                            id="table-all-search"
                            aria-describedby="table-all-search-messages"
                            value={globalFilter ?? ''}
                            onChange={(value) => setGlobalFilter(String(value))}
                            className="fr-input"
                            placeholder={t('example: archives 2012...')}
                        />
                        <div
                            className="fr-messages-group"
                            id="table-all-search-messages"
                            aria-live="polite"
                        ></div>
                    </div>
                    <div>
                        <Filter
                            column={businessColumn}
                            table={table}
                            label={t('Business field')}
                        />
                    </div>
                </div>
                <div className="fr-table__wrapper">
                    <div className="fr-table__container">
                        <div className="fr-table__content">
                            <table
                                id="circulars-table"
                                className="fr-cell--multiline"
                            >
                                <caption>{t('Circulars')}</caption>
                                <thead>
                                    {table
                                        .getHeaderGroups()
                                        .map((headerGroup) => (
                                            <tr key={headerGroup.id}>
                                                {headerGroup.headers.map(
                                                    (header) => {
                                                        return (
                                                            // @ts-expect-error
                                                            <th
                                                                key={header.id}
                                                                scope="col"
                                                                aria-sort={
                                                                    header.column.getIsSorted()
                                                                        ? (header.column.getIsSorted() as string) +
                                                                          'ending'
                                                                        : 'none'
                                                                }
                                                            >
                                                                {' '}
                                                                {!header.column.getCanSort() ? null : (
                                                                    <div
                                                                        {...{
                                                                            className:
                                                                                header.column.getCanSort()
                                                                                    ? 'fr-cell--sort'
                                                                                    : 'fr-cell--fixed',
                                                                            onClick:
                                                                                header.column.getToggleSortingHandler(),
                                                                        }}
                                                                    >
                                                                        {flexRender(
                                                                            header
                                                                                .column
                                                                                .columnDef
                                                                                .header,
                                                                            header.getContext(),
                                                                        )}
                                                                        <button
                                                                            aria-sorting={
                                                                                // DSFR CSS based on inexhisting aria-sorting
                                                                                header.column.getIsSorted() as string
                                                                            }
                                                                            className="fr-btn fr-btn--sort fr-btn-sm"
                                                                        >
                                                                            t('Sort')
                                                                        </button>
                                                                    </div>
                                                                )}
                                                            </th>
                                                        )
                                                    },
                                                )}
                                            </tr>
                                        ))}
                                </thead>
                                <tbody>
                                    {table.getRowModel().rows.map((row) => (
                                        <tr key={row.id}>
                                            {row
                                                .getVisibleCells()
                                                .map((cell) => (
                                                    <td key={cell.id}>
                                                        {flexRender(
                                                            cell.column
                                                                .columnDef.cell,
                                                            cell.getContext(),
                                                        )}
                                                    </td>
                                                ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div className="fr-table__footer">
                    <div className="fr-table__footer--start">
                        <p className="fr-table__detail">
                            {tableSize} {tableSizeLabel}
                        </p>
                        <div className="fr-select-group">
                            <label
                                className="fr-sr-only fr-label"
                                htmlFor="table-footer-select-lignes"
                            >
                                {t('Number of rows per page')}
                            </label>
                            <select
                                className="fr-select"
                                id="table-footer-select-lignes"
                                aria-describedby="table-footer-select-lignes-messages"
                                defaultValue={
                                    table.getState().pagination.pageSize
                                }
                                value={table.getState().pagination.pageSize}
                                onChange={(e) =>
                                    table.setPageSize(Number(e.target.value))
                                }
                            >
                                <option value="" selected disabled>
                                    {t('Number of rows per page')}
                                </option>
                                {['10', '20', '30', '40', '50'].map((value) => {
                                    return (
                                        <option value={value} key={value}>
                                            {value}
                                        </option>
                                    )
                                })}
                            </select>
                            <div
                                className="fr-messages-group"
                                id="table-footer-select-lignes-messages"
                                aria-live="polite"
                            ></div>
                        </div>
                    </div>
                    <div className="fr-table__footer--middle">
                        <Pagination table={table} />
                    </div>
                </div>
            </div>
        </div>
    )
}

const ALL_OPTIONS = [{value: '', label: t('-- All --')}]

function jumpToTop() {
    window.location.hash = '#tableUp'
}

export function Pagination({table}: {table: Table<ICircular>}) {
    const currentPage = table.getState().pagination.pageIndex + 1
    const pageSize = table.getPageCount()

    let pagesToShow = Array()
    pagesToShow.push(1)
    if (1 < currentPage && currentPage < pageSize) {
        if (currentPage - 1 > 1) {
            pagesToShow.push(currentPage - 1)
        }
        pagesToShow.push(currentPage)
        if (currentPage + 1 < pageSize) {
            pagesToShow.push(currentPage + 1)
        }
    }
    if (currentPage == 1) {
        pagesToShow.push(currentPage + 1)
    } else if (currentPage == pageSize) {
        pagesToShow.push(currentPage - 1)
    }
    pagesToShow.push(pageSize)

    let previous = 0
    let links = Array()
    pagesToShow.forEach((page, idx) => {
        if (previous + 1 !== page) {
            links.push(
                <li
                    key={`li-${idx}-e`}
                    className="fr-pagination__item fr-ellipsis"
                >
                    <span>&#8230;</span>
                </li>,
            )
        }
        links.push(
            <li key={`li-${idx}`}>
                <button
                    className="fr-pagination__link"
                    title={`Page ${page}`}
                    aria-current={currentPage === page ? 'page' : undefined}
                    onClick={() => {
                        table.setPageIndex(page - 1)
                        jumpToTop()
                    }}
                >
                    {page}
                </button>
            </li>,
        )
        previous = page
    })
    return (
        <nav
            role="navigation"
            className="fr-pagination"
            aria-label="Pagination"
        >
            <ul className="fr-pagination__list">
                <li>
                    <button
                        className="fr-pagination__link fr-pagination__link--prev fr-pagination__link--lg-label"
                        aria-disabled={!table.getCanPreviousPage()}
                        onClick={() => {
                            table.previousPage()
                            jumpToTop()
                        }}
                        disabled={!table.getCanPreviousPage()}
                        role="link"
                    >
                        {t('Previous page')}
                    </button>
                </li>
                {links.map((element) => element)}
                <li>
                    <button
                        className="fr-pagination__link fr-pagination__link--next fr-pagination__link--lg-label"
                        onClick={() => {
                            table.nextPage()
                            jumpToTop()
                        }}
                        disabled={!table.getCanNextPage()}
                    >
                        {t('Next page')}
                    </button>
                </li>
            </ul>
        </nav>
    )
}

function Filter<T>({
    column,
    table,
    label,
}: {
    column: Column<ICircular>
    table: Table<ICircular>
    label: string
}) {
    const columnFilterValue = column.getFilterValue()
    const sortedUniqueValues = React.useMemo(() => {
        if (['status'].includes(column.id)) {
            return Array.from(column.getFacetedUniqueValues().keys()).sort()
        } else if (column.id === 'business') {
            var values = table
                .getCoreRowModel()
                .flatRows.map((row) =>
                    row.getValue<string>(column.id).split(', '),
                )
            return Array.from(new Set(values.flat())).sort()
        } else {
            return []
        }
    }, [table, column.id, column.getFacetedUniqueValues()])

    const uniqueValues = React.useMemo(() => {
        const values = table
            .getCoreRowModel()
            .flatRows.map((row) => row.getValue(column.id)) as string[]
        return Array.from(new Set(values))
    }, [table, column.id])
    return ['status', 'business'].includes(column.id) ? (
        <DebouncedSelect
            id={'table-' + column.id + '-search'}
            label={label}
            placeholder={t('Select a domain')}
            value={(columnFilterValue ?? '') as string}
            options={ALL_OPTIONS.concat(
                sortedUniqueValues.slice(0, 500).map((value: any) => ({
                    value: value,
                    label: value,
                })),
            )}
            onChange={(value) => column.setFilterValue(value)}
        />
    ) : (
        <DebouncedInput
            id={'table-' + column.id + '-search'}
            type="text"
            value={(columnFilterValue ?? '') as string}
            onChange={(value) => column.setFilterValue(value)}
            placeholder={`... (${column.getFacetedUniqueValues().size})`}
            className="fr-input fa-input--white fr-text--sm fr-mt-1v"
            list={column.id + 'list'}
        />
    )
}
