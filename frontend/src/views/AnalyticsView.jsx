import React, { useState, useEffect, useMemo } from 'react';
import {
    LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    ReferenceLine, Label, LabelList
} from 'recharts';
import { fetchAnalyticsCharts } from '../api/analytics';
import { AnalyticsDrillDownModal } from '../components/AnalyticsDrillDownModal';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#8dd1e1'];

// Fixed color mappings for consistent colors across charts
const FACULTY_COLORS = {
    'Whole School': '#0088FE',
    'N/A': '#0088FE',  // Same as Whole School (backend uses N/A)
    'English': '#00C49F',
    'Mathematics': '#FFBB28',
    'Science': '#FF8042',
    'Humanities': '#8884d8',
    'Arts': '#82ca9d',
    'Technology': '#ffc658',
    'Languages': '#8dd1e1',
    'Health & PE': '#ff6b6b',
    'Business': '#4ecdc4',
    'Music': '#a55eea',
    'Drama': '#fd79a8',
    'Visual Arts': '#fdcb6e',
    'Design': '#6c5ce7',
    'Digital Tech': '#00b894',
    'Food Tech': '#e17055',
    'Media': '#74b9ff',
};

const CONTENT_TYPE_COLORS = {
    // Actual content types from data
    'Guidance & Information': '#0088FE',
    'Promotional': '#00C49F',
    'Student Work': '#FFBB28',
    'Learning Content': '#FF8042',
    'Announcements': '#8884d8',
    // Legacy/additional types
    'Assembly': '#82ca9d',
    'Podcast': '#ffc658',
    'Interview': '#8dd1e1',
    'Presentation': '#ff6b6b',
    'Performance': '#4ecdc4',
    'Announcement': '#8884d8',  // Same as Announcements
    'Tutorial': '#a55eea',
    'News': '#fd79a8',
    'Discussion': '#fdcb6e',
    'Documentary': '#6c5ce7',
    'Event': '#00b894',
    'Sports': '#e17055',
    'Music': '#74b9ff',
    'Drama': '#fab1a0',
    'Other': '#b2bec3',
};

// Helper to get color for faculty
const getFacultyColor = (name, index) => {
    return FACULTY_COLORS[name] || COLORS[index % COLORS.length];
};

// Helper to get color for content type
const getContentTypeColor = (name, index) => {
    return CONTENT_TYPE_COLORS[name] || COLORS[index % COLORS.length];
};

// Helper to parse date from chart key (YYYY-MM-DD or YYYY-Www)
const getDateFromKey = (value) => {
    if (!value) return null;

    // YYYY-MM-DD
    if (value.length === 10 && value.includes('-') && !value.includes('W')) {
        return new Date(value);
    }

    // YYYY-Www
    if (value.includes('-W')) {
        const [yearStr, weekStr] = value.split('-W');
        if (yearStr && weekStr) {
            const year = parseInt(yearStr);
            const week = parseInt(weekStr);

            // SQLite %W: Week 01 is the first week with a Monday.
            // Find the first Monday of the year
            let date = new Date(year, 0, 1);
            while (date.getDay() !== 1) {
                date.setDate(date.getDate() + 1);
            }

            // Add (week - 1) weeks to the first Monday
            // Note: If week is 00, this subtracts 1 week, correctly finding the partial week before the first Monday
            date.setDate(date.getDate() + (week - 1) * 7);

            return date;
        }
    }

    return null;
};

// School Term start dates
const TERMS = [
    { label: 'Term 1', month: 0, day: 27 }, // Jan 27
    { label: 'Term 2', month: 3, day: 19 }, // Apr 19
    { label: 'Term 3', month: 6, day: 12 }, // Jul 12
    { label: 'Term 4', month: 9, day: 4 },  // Oct 4
];

// School Holiday start dates (Inferred)
const HOLIDAYS = [
    { label: 'Summer Hols', month: 0, day: 1 },  // Jan 1 (Start of year gap)
    { label: 'Autumn Hols', month: 3, day: 2 },  // Apr 2
    { label: 'Winter Hols', month: 5, day: 26 }, // Jun 26
    { label: 'Spring Hols', month: 8, day: 18 }, // Sep 18
    { label: 'Summer Hols', month: 11, day: 18 },// Dec 18
];

// Custom label for vertical bars - shows value on top of bar
const renderBarLabel = (props) => {
    const { x, y, width, height, value } = props;
    if (!value || value === 0) return null;

    // Format value: show 1 decimal for hours, whole numbers for counts
    const displayValue = Number.isInteger(value) ? value : value.toFixed(1);

    // Only show label if bar is tall enough (height > 20px)
    if (height < 20) {
        return (
            <text
                x={x + width / 2}
                y={y - 5}
                fill="#374151"
                textAnchor="middle"
                fontSize={11}
                fontWeight="500"
            >
                {displayValue}
            </text>
        );
    }

    return (
        <text
            x={x + width / 2}
            y={y + height / 2 + 4}
            fill="#fff"
            textAnchor="middle"
            fontSize={11}
            fontWeight="600"
        >
            {displayValue}
        </text>
    );
};

// Custom label for horizontal bars - shows value at end of bar
const renderHorizontalBarLabel = (props) => {
    const { x, y, width, height, value } = props;
    if (!value || value === 0) return null;

    const displayValue = Number.isInteger(value) ? value : value.toFixed(1);

    // If bar is wide enough (>40px), show label inside
    if (width > 40) {
        return (
            <text
                x={x + width - 8}
                y={y + height / 2 + 4}
                fill="#fff"
                textAnchor="end"
                fontSize={11}
                fontWeight="600"
            >
                {displayValue}
            </text>
        );
    }

    // Otherwise show label outside the bar
    return (
        <text
            x={x + width + 5}
            y={y + height / 2 + 4}
            fill="#374151"
            textAnchor="start"
            fontSize={11}
            fontWeight="500"
        >
            {displayValue}
        </text>
    );
};

// Custom label for pie/donut charts
const renderPieLabel = (props) => {
    const { cx, cy, midAngle, innerRadius, outerRadius, percent, value, name } = props;

    if (!value || value === 0) return null;

    const RADIAN = Math.PI / 180;
    // Position label in the middle of the arc segment
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    // Only show label if segment is large enough (>5%)
    if (percent < 0.05) return null;

    const displayValue = Number.isInteger(value) ? value : value.toFixed(1);

    return (
        <text
            x={x}
            y={y}
            fill="#fff"
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={11}
            fontWeight="600"
        >
            {displayValue}
        </text>
    );
};

// Custom label for small pie segments - positioned outside
const renderPieLabelLine = (props) => {
    const { cx, cy, midAngle, outerRadius, percent, value, name } = props;

    if (!value || value === 0 || percent >= 0.05) return null;

    const RADIAN = Math.PI / 180;
    const radius = outerRadius + 20;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    const displayValue = Number.isInteger(value) ? value : value.toFixed(1);

    return (
        <text
            x={x}
            y={y}
            fill="#374151"
            textAnchor={x > cx ? 'start' : 'end'}
            dominantBaseline="central"
            fontSize={10}
            fontWeight="500"
        >
            {displayValue}
        </text>
    );
};

export function AnalyticsView() {
    const [timeRange, setTimeRange] = useState('all');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [drillDownConfig, setDrillDownConfig] = useState({
        isOpen: false,
        title: '',
        filters: {},
        filterType: null,
        filterValue: null
    });

    useEffect(() => {
        loadData();
    }, [timeRange]);

    const loadData = async () => {
        setLoading(true);
        try {
            const result = await fetchAnalyticsCharts(timeRange);

            // Frontend override: Rename 'N/A' faculty to 'Whole School'
            if (result?.content_hours_faculty) {
                result.content_hours_faculty = result.content_hours_faculty.map(item => ({
                    ...item,
                    name: item.name === 'N/A' ? 'Whole School' : item.name
                }));
            }

            setData(result);
            setError(null);
        } catch (err) {
            console.error(err);
            setError('Failed to load analytics data');
        } finally {
            setLoading(false);
        }
    };

    // Helper to generate term and holiday lines
    const getReferenceLines = () => {
        if (!data?.recording_volume || data.recording_volume.length === 0) return [];

        const lines = [];
        const volumeData = data.recording_volume;

        // Get year range from data
        const dates = volumeData.map(d => getDateFromKey(d.name)).filter(d => d);
        if (dates.length === 0) return [];

        const minYear = Math.min(...dates.map(d => d.getFullYear()));
        const maxYear = Math.max(...dates.map(d => d.getFullYear()));

        // Track added holiday lines to avoid duplicates
        const addedHolidays = [];

        for (let year = minYear; year <= maxYear; year++) {
            // Add Term Lines
            TERMS.forEach(term => {
                const termDate = new Date(year, term.month, term.day);
                // Find closest data point
                const closest = volumeData.reduce((prev, curr) => {
                    const currDate = getDateFromKey(curr.name);
                    const prevDate = getDateFromKey(prev.name);
                    if (!currDate) return prev;
                    if (!prevDate) return curr;

                    return (Math.abs(currDate - termDate) < Math.abs(prevDate - termDate)) ? curr : prev;
                });

                // Only add if very close (within 4 days) to ensure it snaps to the correct week
                const closestDate = getDateFromKey(closest.name);
                if (closestDate && Math.abs(closestDate - termDate) < 4 * 24 * 60 * 60 * 1000) {
                    lines.push(
                        <ReferenceLine key={`term-${year}-${term.label}`} x={closest.name} stroke="#ff7300" strokeDasharray="3 3">
                            <Label value={term.label} position="insideTopLeft" fill="#ff7300" fontSize={10} />
                        </ReferenceLine>
                    );
                }
            });

            // Add Holiday Lines
            HOLIDAYS.forEach(hol => {
                const holDate = new Date(year, hol.month, hol.day);

                // Check if we already added a similar holiday recently (within 45 days)
                // This handles the overlap between Dec 18 and Jan 1
                const isDuplicate = addedHolidays.some(added =>
                    added.label === hol.label &&
                    Math.abs(added.date - holDate) < 45 * 24 * 60 * 60 * 1000
                );

                if (isDuplicate) return;

                // Find closest data point
                const closest = volumeData.reduce((prev, curr) => {
                    const currDate = getDateFromKey(curr.name);
                    const prevDate = getDateFromKey(prev.name);
                    if (!currDate) return prev;
                    if (!prevDate) return curr;

                    return (Math.abs(currDate - holDate) < Math.abs(prevDate - holDate)) ? curr : prev;
                });

                const closestDate = getDateFromKey(closest.name);
                // Only add if very close (within 4 days)
                if (closestDate && Math.abs(closestDate - holDate) < 4 * 24 * 60 * 60 * 1000) {
                    lines.push(
                        <ReferenceLine key={`hol-${year}-${hol.label}-${hol.month}`} x={closest.name} stroke="#82ca9d" strokeDasharray="3 3">
                            <Label value={hol.label} position="insideTopLeft" fill="#82ca9d" fontSize={10} />
                        </ReferenceLine>
                    );
                    addedHolidays.push({ label: hol.label, date: holDate });
                }
            });
        }

        return lines;
    };

    // Helper to format X-axis labels
    const formatXAxis = (value, index) => {
        const dateObj = getDateFromKey(value);
        if (!dateObj) return value;

        // Short ranges (Day view): Show Date (e.g., "Jul 1st")
        if (timeRange === '7d' || timeRange === '30d') {
            const day = dateObj.getDate();
            const suffix = ["th", "st", "nd", "rd"][(day % 10 > 3) ? 0 : (day % 100 - day % 10 !== 10) * day % 10];
            return dateObj.toLocaleDateString('en-AU', { month: 'short' }) + ` ${day}${suffix}`;
        }

        // Long ranges (Week view): Show Month (e.g., "July")
        // Use "Middle of Week" logic to determine which month this week belongs to
        const middle = new Date(dateObj);
        middle.setDate(middle.getDate() + 3); // Add 3 days to get to Thursday (middle of week)
        const currentMonth = middle.toLocaleDateString('en-AU', { month: 'long' });

        // Always show label for the first data point
        if (index === 0) {
            return currentMonth;
        }

        // For subsequent points, compare with the ACTUAL previous data point
        // This prevents duplicate labels when weeks are close but logic assumes 7 days
        const prevValue = data?.recording_volume?.[index - 1]?.name;
        if (prevValue) {
            const prevDate = getDateFromKey(prevValue);
            if (prevDate) {
                const prevMiddle = new Date(prevDate);
                prevMiddle.setDate(prevMiddle.getDate() + 3);
                const prevMonth = prevMiddle.toLocaleDateString('en-AU', { month: 'long' });

                if (currentMonth !== prevMonth) {
                    return currentMonth;
                }
                return '';
            }
        }

        return '';
    };

    // Helper to format Tooltip labels
    const formatTooltip = (value) => {
        const dateObj = getDateFromKey(value);
        if (!dateObj) return value;

        // Short ranges (Day view): Show Day Name (e.g., "Monday")
        if (timeRange === '7d' || timeRange === '30d') {
            return dateObj.toLocaleDateString('en-AU', { weekday: 'long', month: 'short', day: 'numeric' });
        }

        // Long ranges (Week view): Show "Week X" or "Term X Week Y"
        const year = dateObj.getFullYear();
        const month = dateObj.getMonth();
        const date = dateObj.getDate();
        const mmdd = (month + 1) * 100 + date;

        // Check Terms
        // Term 1: 27 Jan (127) to 1 Apr (401)
        if (mmdd >= 127 && mmdd <= 401) {
            const termStart = new Date(year, 0, 27);
            const diffTime = Math.abs(dateObj - termStart);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            const termWeek = Math.floor(diffDays / 7) + 1;
            return `Term 1 Week ${termWeek}`;
        }
        // Term 2: 19 Apr (419) to 25 Jun (625)
        if (mmdd >= 419 && mmdd <= 625) {
            const termStart = new Date(year, 3, 19);
            const diffTime = Math.abs(dateObj - termStart);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            const termWeek = Math.floor(diffDays / 7) + 1;
            return `Term 2 Week ${termWeek}`;
        }
        // Term 3: 12 Jul (712) to 17 Sep (917)
        if (mmdd >= 712 && mmdd <= 917) {
            const termStart = new Date(year, 6, 12);
            const diffTime = Math.abs(dateObj - termStart);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            const termWeek = Math.floor(diffDays / 7) + 1;
            return `Term 3 Week ${termWeek}`;
        }
        // Term 4: 4 Oct (1004) to 17 Dec (1217)
        if (mmdd >= 1004 && mmdd <= 1217) {
            const termStart = new Date(year, 9, 4);
            const diffTime = Math.abs(dateObj - termStart);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            const termWeek = Math.floor(diffDays / 7) + 1;
            return `Term 4 Week ${termWeek}`;
        }

        // Fallback: Week of [Date]
        return `Week of ${dateObj.toLocaleDateString('en-AU', { month: 'short', day: 'numeric' })}`;
    };

    // Helper to calculate Y-axis domain with padding
    const calculateYDomain = (data) => {
        if (!data || data.length === 0) return [0, 'auto'];

        const max = Math.max(...data.map(d => d.value));
        const ceil = Math.ceil(max);

        // If max is close to the ceiling (within 0.2), add extra headroom
        const domainMax = max > (ceil - 0.2) ? ceil + 1 : ceil;

        return [0, domainMax];
    };

    // Helper to format duration (seconds -> Xh Ym)
    const formatDuration = (seconds) => {
        if (!seconds) return '0h 0m';
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    };

    // Handle Chart Click
    const handleChartClick = (entry, type) => {
        console.log('handleChartClick', entry, type);
        if (!entry) return;

        // Recharts sends different data structures depending on the chart type
        // For Bar/Pie, entry usually has 'name' or 'activeLabel' or 'payload'
        const value = entry.name || entry.activeLabel || (entry.payload && entry.payload.name);
        console.log('handleChartClick value:', value);

        if (!value) {
            console.warn('Could not determine value from click:', entry);
            return;
        }

        let filters = {};
        let filterType = null; // NEW: Track explicit filter type
        let filterValue = null;
        let title = '';

        switch (type) {
            case 'volume':
                // Volume is special: it uses date ranges, not a specific category
                const date = getDateFromKey(value);
                if (date) {
                    const dateStr = date.toISOString().split('T')[0];
                    if (value.includes('W')) {
                        const endDate = new Date(date);
                        endDate.setDate(endDate.getDate() + 6);
                        filters = {
                            start_date: dateStr,
                            end_date: endDate.toISOString().split('T')[0]
                        };
                        title = `Recordings for Week of ${date.toLocaleDateString()}`;
                    } else {
                        filters = { start_date: dateStr, end_date: dateStr };
                        title = `Recordings for ${date.toLocaleDateString()}`;
                    }
                }
                break;
            case 'faculty':
                filterType = 'faculty'; // NEW
                // Map 'Whole School' back to 'N/A' for the backend query
                filterValue = value === 'Whole School' ? 'N/A' : value;
                title = `Recordings for ${value}`;
                break;
            case 'speaker_count':
                const count = parseInt(value.split(' ')[0]);
                if (!isNaN(count)) {
                    // Let's stick to filters for numeric values for safety unless we confirm backend support.
                    filters = { speaker_count: count };
                    title = `Recordings with ${value}`;
                }
                break;
            case 'audience':
                filterType = 'audience'; // NEW
                filterValue = value;
                title = `Recordings for ${value}`;
                break;
            case 'speaker_demographics':
                filterType = 'speaker_type'; // NEW (Mapped to 'speaker' in backend)
                filterValue = value;
                title = `Recordings with ${value} Speakers`;
                break;
            case 'content_type':
                filterType = 'content_type'; // NEW
                filterValue = value;
                title = `${value} Recordings`;
                break;
            case 'faculty_output':
                filterType = 'faculty'; // NEW
                // Map 'Whole School' back to 'N/A' for the backend query
                filterValue = value === 'Whole School' ? 'N/A' : value;
                title = `Output for ${value}`;
                break;
            case 'campus':
                filterType = 'campus';
                filterValue = value;
                title = `${value} Campus Content`;
                break;
            case 'language':
                filterType = 'language';
                filterValue = value;
                title = `Language: ${value}`;
                break;
            case 'video_duration':
                filterType = 'duration_range';
                filterValue = value;
                title = `Videos with Duration: ${value}`;
                break;
            default:
                return;
        }

        setDrillDownConfig({
            isOpen: true,
            title,
            filters,    // Used for complex ranges (dates)
            filterType, // Used for categories (Faculty, Audience, etc)
            filterValue,
            timeRange   // Pass the global time range context
        });
    };

    if (loading && !data) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full text-red-600">
                {error}
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto bg-gray-50 p-6 relative">
            {/* Inject styles to remove focus outlines */}
            <style>{`
                .recharts-surface:focus { outline: none !important; }
                .recharts-wrapper:focus { outline: none !important; }
                div[role="region"]:focus { outline: none !important; }
                path:focus { outline: none !important; }
                g:focus { outline: none !important; }
            `}</style>

            {/* Drill Down Modal */}
            <AnalyticsDrillDownModal
                isOpen={drillDownConfig.isOpen}
                onClose={() => setDrillDownConfig(prev => ({ ...prev, isOpen: false }))}
                title={drillDownConfig.title}
                filters={drillDownConfig.filters}
                filterType={drillDownConfig.filterType}   // NEW
                filterValue={drillDownConfig.filterValue} // NEW
                timeRange={timeRange}                     // NEW
            />

            {/* Header & Controls */}
            <div className="flex justify-between items-center mb-8">
                <h1 className="text-2xl font-bold text-gray-800">Analytics Dashboard</h1>

                <div className="flex bg-white rounded-lg shadow-sm border border-gray-200 p-1">
                    {[
                        { id: 'all', label: 'All Time' },
                        { id: '2025', label: '2025' },
                        { id: '2024', label: '2024' },
                        { id: '12m', label: 'Past 12 Months' },
                        { id: '6m', label: 'Past 6 Months' },
                        { id: '30d', label: 'Past 30 Days' },
                        { id: '7d', label: 'Past Week' },
                    ].map((range) => (
                        <button
                            key={range.id}
                            onClick={() => setTimeRange(range.id)}
                            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${timeRange === range.id
                                ? 'bg-blue-100 text-blue-700'
                                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                                }`}
                        >
                            {range.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 pb-12">
                {/* 1. Recording Volume Over Time */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 relative group hover:border-blue-200 transition-colors">
                    <div className="flex justify-between items-start mb-4">
                        <h3 className="text-lg font-semibold text-gray-700">Recording Volume Over Time</h3>
                        {/* Total Duration Sub-card */}
                        <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-2 flex flex-col items-end">
                            <span className="text-xs text-blue-600 font-medium uppercase tracking-wide">Total Duration</span>
                            <span className="text-xl font-bold text-blue-800">
                                {formatDuration(data?.total_duration_seconds)}
                            </span>
                        </div>
                    </div>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={data?.recording_volume || []}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis
                                    dataKey="name"
                                    tickFormatter={formatXAxis}
                                    interval={0}
                                    minTickGap={30}
                                />
                                <YAxis
                                    allowDecimals={false}
                                    domain={calculateYDomain(data?.recording_volume)}
                                    type="number"
                                />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    labelStyle={{ color: '#111827', fontWeight: '600', marginBottom: '0.5rem' }}
                                    labelFormatter={formatTooltip}
                                />
                                <Legend />
                                {getReferenceLines()}
                                <Bar
                                    dataKey="value"
                                    name="Hours"
                                    fill="#2563eb"
                                    radius={[4, 4, 0, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'volume')}
                                    isAnimationActive={false}
                                >
                                    <LabelList dataKey="value" content={renderBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Quick Stats Row - 4 small cards */}
                {/* Totals Card */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Content Totals</h3>
                    <div className="h-64 flex flex-col justify-center space-y-6">
                        <div className="text-center">
                            <div className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Total Content Hours</div>
                            <div className="text-3xl font-bold text-blue-600">
                                {data?.total_duration_seconds ? (data.total_duration_seconds / 3600).toFixed(1) : '0'}h
                            </div>
                        </div>
                        <div className="border-t border-gray-100"></div>
                        <div className="text-center">
                            <div className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Total Video Count</div>
                            <div className="text-3xl font-bold text-green-600">
                                {data?.total_videos ?? 0}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Campus Content Hours (Donut) */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Campus (Content Hours)</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={data?.campus_dist || []}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                    onClick={(data) => handleChartClick(data, 'campus')}
                                    className="cursor-pointer"
                                    label={renderPieLabel}
                                    labelLine={false}
                                    isAnimationActive={false}
                                >
                                    {data?.campus_dist?.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip
                                    formatter={(value) => [`${value}h`, 'Content']}
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                />
                                <Legend verticalAlign="bottom" height={36} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Speaker Demographics */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Speaker Demographics</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={data?.speaker_dist || []}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                    onClick={(data) => handleChartClick(data, 'speaker_demographics')}
                                    className="cursor-pointer"
                                    label={renderPieLabel}
                                    labelLine={false}
                                    isAnimationActive={false}
                                >
                                    {data?.speaker_dist?.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip />
                                <Legend verticalAlign="bottom" height={36} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Languages Spoken */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Languages Spoken</h3>
                    <div className="h-64 overflow-y-auto pr-2">
                        {data?.language_dist && data.language_dist.length > 0 ? (
                            <div className={`grid gap-3 ${data.language_dist.length <= 3 ? 'grid-cols-1' : 'grid-cols-2'}`}>
                                {data.language_dist.map((lang, index) => (
                                    <div
                                        key={index}
                                        onClick={() => handleChartClick({ name: lang.name }, 'language')}
                                        className={`flex items-center justify-between rounded-lg bg-gray-50 border border-gray-100 hover:bg-blue-50 hover:border-blue-100 transition-colors cursor-pointer ${data.language_dist.length <= 3 ? 'p-4' : 'p-3'
                                            }`}
                                    >
                                        <span className={`font-medium text-gray-700 truncate ${data.language_dist.length <= 3 ? 'text-base' : 'text-sm'
                                            }`} title={lang.name}>
                                            {lang.name}
                                        </span>
                                        <span className={`font-semibold bg-white text-gray-500 rounded border border-gray-200 ${data.language_dist.length <= 3 ? 'text-sm px-3 py-1.5' : 'text-xs px-2 py-1'
                                            }`}>
                                            {lang.value}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <span className="text-sm">No language data</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* 2. Total Content Hours per Faculty */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Total Content Hours per Faculty</h3>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={data?.content_hours_faculty || []}
                                layout="vertical"
                            >
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                <XAxis type="number" />
                                <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 12 }} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    cursor={{ fill: 'transparent' }}
                                />
                                <Bar
                                    dataKey="value"
                                    name="Hours"
                                    fill="#8884d8"
                                    radius={[0, 4, 4, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'faculty')}
                                    isAnimationActive={false}
                                >
                                    {data?.content_hours_faculty?.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={getFacultyColor(entry.name, index)} />
                                    ))}
                                    <LabelList dataKey="value" content={renderHorizontalBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 3. Content Type Distribution (Hours) */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Content Hours by Type</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={data?.content_type_dist || []}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="name" />
                                <YAxis allowDecimals={false} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    cursor={{ fill: 'transparent' }}
                                />
                                <Bar
                                    dataKey="value"
                                    name="Hours"
                                    fill="#00C49F"
                                    radius={[4, 4, 0, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'content_type')}
                                    isAnimationActive={false}
                                >
                                    {data?.content_type_dist?.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={getContentTypeColor(entry.name, index)} />
                                    ))}
                                    <LabelList dataKey="value" content={renderBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 7. Faculty Count - Horizontal Bar Chart */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Recordings per Faculty (Total Count)</h3>
                    <div className="h-80">
                        {data?.faculty_count_dist && data.faculty_count_dist.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={data.faculty_count_dist}
                                    layout="vertical"
                                >
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                    <XAxis type="number" allowDecimals={false} />
                                    <YAxis
                                        dataKey="name"
                                        type="category"
                                        width={120}
                                        tick={{ fontSize: 12 }}
                                        tickFormatter={(value) => value === 'N/A' ? 'Whole School' : value}
                                    />
                                    <Tooltip
                                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                        cursor={{ fill: 'transparent' }}
                                        formatter={(value, name, props) => [value, 'Count']}
                                        labelFormatter={(label) => label === 'N/A' ? 'Whole School' : label}
                                    />
                                    <Bar
                                        dataKey="value"
                                        name="Count"
                                        fill="#8884d8"
                                        radius={[0, 4, 4, 0]}
                                        className="cursor-pointer"
                                        onClick={(data) => handleChartClick(data, 'faculty')}
                                        isAnimationActive={false}
                                    >
                                        {data?.faculty_count_dist?.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={getFacultyColor(entry.name, index)} />
                                        ))}
                                        <LabelList dataKey="value" content={renderHorizontalBarLabel} />
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <span className="text-sm">No faculty data</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* 9. Content Type Count - Column Chart */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Content Type (Total Count)</h3>
                    <div className="h-64">
                        {data?.content_type_count_dist && data.content_type_count_dist.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={data.content_type_count_dist}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="name" />
                                    <YAxis allowDecimals={false} />
                                    <Tooltip
                                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                        cursor={{ fill: 'transparent' }}
                                    />
                                    <Bar
                                        dataKey="value"
                                        name="Count"
                                        fill="#00C49F"
                                        radius={[4, 4, 0, 0]}
                                        className="cursor-pointer"
                                        onClick={(data) => handleChartClick(data, 'content_type')}
                                        isAnimationActive={false}
                                    >
                                        {data?.content_type_count_dist?.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={getContentTypeColor(entry.name, index)} />
                                        ))}
                                        <LabelList dataKey="value" content={renderBarLabel} />
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <span className="text-sm">No content type data</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* 10. Video Duration Distribution */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 lg:col-span-4 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Video Duration Distribution</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={data?.video_duration_dist || []}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="name" />
                                <YAxis allowDecimals={false} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    cursor={{ fill: 'transparent' }}
                                />
                                <Bar
                                    dataKey="value"
                                    name="Videos"
                                    fill="#8884d8"
                                    radius={[4, 4, 0, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'video_duration')}
                                    isAnimationActive={false}
                                >
                                    <LabelList dataKey="value" content={renderBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 11. Speaker Count Distribution */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Speaker Count Distribution</h3>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={data?.speaker_count_dist || []}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="name" label={{ value: 'Speakers', position: 'insideBottom', offset: -5 }} />
                                <YAxis allowDecimals={false} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    cursor={{ fill: 'transparent' }}
                                />
                                <Bar
                                    dataKey="value"
                                    name="Videos"
                                    fill="#82ca9d"
                                    radius={[4, 4, 0, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'speaker_count')}
                                    isAnimationActive={false}
                                >
                                    <LabelList dataKey="value" content={renderBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 12. Target Audience Analysis */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 group hover:border-blue-200 transition-colors">
                    <h3 className="text-lg font-semibold text-gray-700 mb-4">Target Audience</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={data?.audience_dist || []}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="name" tick={{ fontSize: 12 }} interval={0} angle={-30} textAnchor="end" height={60} />
                                <YAxis allowDecimals={false} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                    cursor={{ fill: 'transparent' }}
                                />
                                <Bar
                                    dataKey="value"
                                    name="Count"
                                    fill="#ffc658"
                                    radius={[4, 4, 0, 0]}
                                    className="cursor-pointer"
                                    onClick={(data) => handleChartClick(data, 'audience')}
                                    isAnimationActive={false}
                                >
                                    <LabelList dataKey="value" content={renderBarLabel} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>


            </div>
        </div>
    );
}