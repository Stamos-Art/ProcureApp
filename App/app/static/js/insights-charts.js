/**
 * Insights Dashboard - ApexCharts Configuration
 * Handles all chart rendering for procurement analytics
 */

function renderAllCharts(data) {
    try {
        // Overview Tab
        if (data.rfq_trends) renderRFQTrendChart(data.rfq_trends);
        if (data.status_distribution) renderStatusDistributionChart(data.status_distribution);

        // Supplier Performance Tab
        if (data.supplier_performance) {
            renderSupplierPerformanceChart(data.supplier_performance);
            renderSupplierBubbleChart(data.supplier_performance);
        }

        // Cost Analysis Tab
        if (data.price_trends) renderCostTrendChart(data.price_trends);
        if (data.supplier_costs) {
            renderCostPieChart(data.supplier_costs);
            renderCostBarChart(data.supplier_costs);
        }

        // Timeline & Delivery Tab
        if (data.timeline_data) {
            renderApprovalDaysChart(data.timeline_data);
            renderOnTimeGaugeChart(data.timeline_data);
            renderFulfillmentDaysChart(data.timeline_data);
        }

        // Risk Analysis Tab
        if (data.risk_scores) renderRiskHeatmapChart(data.risk_scores);
        if (data.risk_data) renderRiskBreakdownChart(data.risk_data);

        // Trends & Forecast Tab
        if (data.rfq_trends) {
            renderSpendForecastChart(data.rfq_trends);
            renderVolumeForecastChart(data.rfq_trends);
        }
    } catch (e) {
        console.error('Error rendering charts:', e);
        showErrorMessage('Error loading charts. Check console for details.');
    }
}

function showErrorMessage(msg) {
    const placeholder = document.querySelector('[id^="chart-"]');
    if (placeholder) {
        placeholder.innerHTML = '<div class="alert alert-danger">' + msg + '</div>';
    }
}

// ============ OVERVIEW TAB ============

function renderRFQTrendChart(data) {
    const chartDiv = document.querySelector('#chart-rfq-trend');
    if (!chartDiv) return;
    
    try {
        if (!data || !data.months || data.months.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No RFQ data available</p>';
            return;
        }

        const options = {
            series: [
                {
                    name: 'RFQ Volume',
                    data: data.volume || []
                }
            ],
            chart: {
                type: 'area',
                height: 350,
                sparkline: { enabled: false },
                toolbar: { show: true }
            },
            colors: ['#007bff'],
            stroke: {
                curve: 'smooth',
                width: 2
            },
            fill: {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.45,
                    opacityTo: 0.05,
                    stops: [20, 100, 100, 100]
                }
            },
            xaxis: {
                categories: data.months || [],
                type: 'datetime'
            },
            yaxis: {
                title: { text: 'Number of RFQs' }
            },
            tooltip: {
                theme: 'light',
                x: { show: true }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering RFQ Trend chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderStatusDistributionChart(statusData) {
    const chartDiv = document.querySelector('#chart-status-distribution');
    if (!chartDiv) return;
    
    try {
        if (!statusData || Object.keys(statusData).length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No status data available</p>';
            return;
        }

        const chartData = Object.entries(statusData).map(([status, count]) => count);
        const chartLabels = Object.keys(statusData).map(s => s.toUpperCase());

        const options = {
            series: chartData,
            chart: {
                type: 'donut',
                height: 350
            },
            labels: chartLabels,
            colors: ['#ffc107', '#007bff', '#28a745', '#dc3545', '#6f42c1', '#17a2b8'],
            legend: {
                position: 'bottom'
            },
            responsive: [{
                breakpoint: 480,
                options: {
                    chart: { width: 200 },
                    legend: { position: 'bottom' }
                }
            }],
            dataLabels: {
                enabled: true,
                formatter: function(val) {
                    return Math.round(val) + '%';
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Status Distribution chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

// ============ SUPPLIER PERFORMANCE TAB ============

function renderSupplierPerformanceChart(suppliersData) {
    const chartDiv = document.querySelector('#chart-supplier-performance');
    if (!chartDiv) return;
    
    try {
        if (!suppliersData || suppliersData.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No supplier data available</p>';
            return;
        }

        const topSuppliers = suppliersData.slice(0, 10);
        const names = topSuppliers.map(s => s.name || 'Unknown');
        const winRates = topSuppliers.map(s => parseFloat(s.win_rate) || 0);
        const onTimeRates = topSuppliers.map(s => parseFloat(s.on_time_rate) || 0);
        const quality = topSuppliers.map(s => parseFloat(s.avg_quality) || 0);

        const options = {
            series: [
                { name: 'Win Rate (%)', data: winRates },
                { name: 'On-Time Rate (%)', data: onTimeRates },
                { name: 'Avg Quality (★)', data: quality }
            ],
            chart: {
                type: 'bar',
                height: 400,
                stacked: false,
                toolbar: { show: true }
            },
            colors: ['#28a745', '#ffc107', '#007bff'],
            xaxis: {
                categories: names,
                destroyed: true
            },
            yaxis: {
                title: { text: 'Performance Score' }
            },
            legend: {
                position: 'top'
            },
            dataLabels: {
                enabled: false
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Supplier Performance chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderSupplierBubbleChart(suppliersData) {
    const chartDiv = document.querySelector('#chart-supplier-bubble');
    if (!chartDiv) return;
    
    try {
        if (!suppliersData || suppliersData.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No supplier data available</p>';
            return;
        }

        const seriesData = suppliersData.map(s => ({
            x: parseFloat(s.win_rate) || 0,
            y: parseFloat(s.on_time_rate) || 0,
            z: parseFloat(s.total_awarded) || 0,
            name: s.name || 'Unknown'
        }));

        const options = {
            series: [{
                name: 'Performance',
                data: seriesData
            }],
            chart: {
                type: 'bubble',
                height: 400,
                toolbar: { show: true }
            },
            xaxis: {
                title: { text: 'Win Rate (%)' },
                min: 0,
                max: 100
            },
            yaxis: {
                title: { text: 'On-Time Delivery (%)' },
                min: 0,
                max: 100
            },
            fill: {
                opacity: 0.8
            },
            tooltip: {
                custom: function({ dataPointIndex }) {
                    if (dataPointIndex < seriesData.length) {
                        const data = seriesData[dataPointIndex];
                        return `<div class="p-2"><strong>${data.name}</strong><br/>Win Rate: ${data.x.toFixed(1)}%<br/>On-Time: ${data.y.toFixed(1)}%<br/>Orders: ${data.z}</div>`;
                    }
                    return '';
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Supplier Bubble chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

// ============ COST ANALYSIS TAB ============

function renderCostTrendChart(trendData) {
    const chartDiv = document.querySelector('#chart-cost-trend');
    if (!chartDiv) return;
    
    try {
        if (!trendData || Object.keys(trendData).length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No cost data available</p>';
            return;
        }

        const series = [];
        const suppliers = Object.keys(trendData);

        suppliers.slice(0, 5).forEach(supplier => {
            series.push({
                name: supplier,
                data: (trendData[supplier].values || []).map(v => parseFloat(v) || 0)
            });
        });

        const firstSupplier = trendData[suppliers[0]];
        const months = firstSupplier ? (firstSupplier.months || []) : [];

        const options = {
            series: series,
            chart: {
                type: 'area',
                height: 400,
                stacked: false,
                toolbar: { show: true }
            },
            colors: ['#007bff', '#28a745', '#ffc107', '#dc3545', '#6f42c1'],
            xaxis: {
                categories: months,
                type: 'datetime'
            },
            yaxis: {
                title: { text: 'Cost (€)' }
            },
            stroke: {
                curve: 'smooth',
                width: 2
            },
            fill: {
                type: 'gradient',
                gradient: {
                    opacityFrom: 0.2,
                    opacityTo: 0
                }
            },
            legend: {
                position: 'top'
            },
            tooltip: {
                theme: 'light',
                y: {
                    formatter: function(val) {
                        return '€' + (val || 0).toFixed(2);
                    }
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Cost Trend chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderCostPieChart(costData) {
    const chartDiv = document.querySelector('#chart-cost-pie');
    if (!chartDiv) return;
    
    try {
        if (!costData || costData.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No data available</p>';
            return;
        }

        const topSuppliers = costData.slice(0, 8);
        const labels = topSuppliers.map(s => s.supplier || 'Unknown');
        const values = topSuppliers.map(s => parseFloat(s.total_cost || 0));

        const options = {
            series: values,
            chart: {
                type: 'pie',
                height: 350
            },
            labels: labels,
            colors: ['#007bff', '#28a745', '#ffc107', '#dc3545', '#6f42c1', '#17a2b8', '#20c997', '#fd7e14'],
            legend: {
                position: 'bottom',
                fontSize: 12
            },
            dataLabels: {
                enabled: true,
                formatter: function(val) {
                    return val.toFixed(1) + '%';
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Cost Pie chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderCostBarChart(costData) {
    const chartDiv = document.querySelector('#chart-cost-bar');
    if (!chartDiv) return;
    
    try {
        if (!costData || costData.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No data available</p>';
            return;
        }

        const topSuppliers = costData.slice(0, 8);
        const labels = topSuppliers.map(s => s.supplier || 'Unknown');
        const values = topSuppliers.map(s => parseFloat(s.total_cost || 0));

        const options = {
            series: [{
                name: 'Total Cost',
                data: values
            }],
            chart: {
                type: 'bar',
                height: 350,
                toolbar: { show: true }
            },
            colors: ['#007bff'],
            xaxis: {
                categories: labels
            },
            yaxis: {
                title: { text: 'Cost (€)' }
            },
            tooltip: {
                theme: 'light',
                y: {
                    formatter: function(val) {
                        return '€' + (val || 0).toFixed(2);
                    }
                }
            },
            dataLabels: {
                enabled: false
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Cost Bar chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

// ============ TIMELINE & DELIVERY TAB ============

function renderApprovalDaysChart(timelineData) {
    const chartDiv = document.querySelector('#chart-approval-days');
    if (!chartDiv) return;
    
    try {
        const statuses = ['PENDING', 'OPEN', 'PENDING_FINAL_APPROVAL'];
        const approvalDays = statuses.map(s => 
            (timelineData && timelineData.avg_approval_days_by_status && timelineData.avg_approval_days_by_status[s]) || 0
        );

        const options = {
            series: [{
                name: 'Avg Days to Approve',
                data: approvalDays
            }],
            chart: {
                type: 'bar',
                height: 300,
                toolbar: { show: true }
            },
            colors: ['#ffc107'],
            xaxis: {
                categories: statuses
            },
            yaxis: {
                title: { text: 'Days' }
            },
            dataLabels: {
                enabled: true,
                formatter: function(val) {
                    return Math.round(val) + ' days';
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Approval Days chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderOnTimeGaugeChart(timelineData) {
    const chartDiv = document.querySelector('#chart-ontime-gauge');
    if (!chartDiv) return;
    
    try {
        const onTimeRate = Math.round((timelineData && timelineData.deadline_compliance) || 0);

        const options = {
            series: [onTimeRate],
            chart: {
                type: 'radialBar',
                height: 300
            },
            plotOptions: {
                radialBar: {
                    startAngle: -90,
                    endAngle: 90,
                    hollow: {
                        margin: 15,
                        size: '70%'
                    },
                    dataLabels: {
                        name: { fontSize: '16px' },
                        value: {
                            fontSize: '24px',
                            formatter: function(val) {
                                return val + '%';
                            }
                        }
                    }
                }
            },
            colors: [onTimeRate > 80 ? '#28a745' : (onTimeRate > 60 ? '#ffc107' : '#dc3545')],
            labels: ['On-Time Delivery']
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering On-Time Gauge chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderFulfillmentDaysChart(timelineData) {
    const chartDiv = document.querySelector('#chart-fulfillment-days');
    if (!chartDiv) return;
    
    try {
        const avgFulfillment = Math.round((timelineData && timelineData.avg_fulfillment_days) || 0);

        const options = {
            series: [{
                name: 'Avg Fulfillment Days',
                data: [avgFulfillment]
            }],
            chart: {
                type: 'bar',
                height: 250,
                toolbar: { show: true }
            },
            colors: ['#17a2b8'],
            xaxis: {
                categories: ['Overall Average']
            },
            yaxis: {
                title: { text: 'Days' }
            },
            dataLabels: {
                enabled: true,
                formatter: function(val) {
                    return Math.round(val) + ' days';
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Fulfillment Days chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

// ============ RISK ANALYSIS TAB ============

function renderRiskHeatmapChart(riskScores) {
    const chartDiv = document.querySelector('#chart-risk-heatmap');
    if (!chartDiv) return;
    
    try {
        if (!riskScores || riskScores.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No risk data available</p>';
            return;
        }

        const topSuppliers = riskScores.slice(0, 10);
        const names = topSuppliers.map(s => s.name || 'Unknown');
        const scores = topSuppliers.map(s => parseFloat(s.risk_score) || 0);

        const options = {
            series: [{
                name: 'Risk Score',
                data: scores
            }],
            chart: {
                type: 'bar',
                height: 350,
                toolbar: { show: true }
            },
            colors: topSuppliers.map(s => {
                const score = parseFloat(s.risk_score) || 0;
                if (score >= 70) return '#dc3545';
                if (score >= 40) return '#ffc107';
                return '#28a745';
            }),
            xaxis: {
                categories: names
            },
            yaxis: {
                title: { text: 'Risk Score (0-100)' },
                min: 0,
                max: 100
            },
            dataLabels: {
                enabled: true,
                formatter: function(val) {
                    return Math.round(val);
                }
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Risk Heatmap chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderRiskBreakdownChart(riskData) {
    const chartDiv = document.querySelector('#chart-risk-breakdown');
    if (!chartDiv) return;
    
    try {
        const riskFactors = [
            { name: 'Defect Rate', value: parseFloat((riskData && riskData.defect_rate) || 0) * 100 },
            { name: 'Single-Bid RFQs', value: parseFloat((riskData && riskData.single_bid_rfq_percentage) || 0) },
            { name: 'Supplier Concentration', value: parseFloat((riskData && riskData.supplier_concentration) || 0) * 100 }
        ];

        const options = {
            series: riskFactors.map(f => f.value),
            chart: {
                type: 'radar',
                height: 350,
                toolbar: { show: true }
            },
            xaxis: {
                categories: riskFactors.map(f => f.name)
            },
            colors: ['#dc3545'],
            fill: {
                opacity: 0.4
            },
            stroke: {
                width: 2
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Risk Breakdown chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

// ============ TRENDS & FORECAST TAB ============

function renderSpendForecastChart(trendData) {
    const chartDiv = document.querySelector('#chart-spend-forecast');
    if (!chartDiv) return;
    
    try {
        const months = (trendData && trendData.months) || [];
        const historicalValues = (trendData && trendData.volume) || [];

        if (historicalValues.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No forecast data available</p>';
            return;
        }

        // Simple extrapolation
        const lastValue = historicalValues[historicalValues.length - 1] || 0;
        const trend = historicalValues.length > 1 ? (lastValue - historicalValues[0]) / (historicalValues.length - 1) : 0;

        const forecastMonths = ['Forecast M+1', 'Forecast M+2', 'Forecast M+3'];
        const forecastValues = [
            lastValue + trend,
            lastValue + (trend * 2),
            lastValue + (trend * 3)
        ];

        const options = {
            series: [
                {
                    name: 'Historical Spend',
                    data: historicalValues.slice(-6).map(v => (v || 0) * 1000)
                },
                {
                    name: 'Forecasted Spend',
                    data: new Array(historicalValues.slice(-6).length - 1).fill(null).concat(forecastValues.map(v => (v || 0) * 1000))
                }
            ],
            chart: {
                type: 'area',
                height: 350,
                stacked: false,
                toolbar: { show: true }
            },
            colors: ['#007bff', '#dc3545'],
            stroke: {
                curve: 'smooth',
                dashArray: [0, 5],
                width: 2
            },
            fill: {
                type: 'gradient',
                opacityFrom: 0.2,
                opacityTo: 0
            },
            xaxis: {
                categories: (months.slice(-6) || []).concat(forecastMonths)
            },
            yaxis: {
                title: { text: 'Spend (€)' }
            },
            tooltip: {
                theme: 'light'
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Spend Forecast chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}

function renderVolumeForecastChart(trendData) {
    const chartDiv = document.querySelector('#chart-volume-forecast');
    if (!chartDiv) return;
    
    try {
        const months = (trendData && trendData.months) || [];
        const volumes = (trendData && trendData.volume) || [];

        if (volumes.length === 0) {
            chartDiv.innerHTML = '<p class="text-muted text-center py-4">No forecast data available</p>';
            return;
        }

        const lastValue = volumes[volumes.length - 1] || 0;
        const trend = volumes.length > 1 ? (lastValue - volumes[0]) / (volumes.length - 1) : 0;

        const forecastMonths = ['Month +1', 'Month +2', 'Month +3'];
        const forecastVolumes = [
            Math.round(lastValue + trend),
            Math.round(lastValue + (trend * 2)),
            Math.round(lastValue + (trend * 3))
        ];

        const options = {
            series: [
                {
                    name: 'RFQ Volume',
                    data: (volumes.slice(-6) || []).map(v => parseFloat(v) || 0)
                },
                {
                    name: 'Forecast',
                    data: new Array((volumes.slice(-6) || []).length - 1).fill(null).concat(forecastVolumes)
                }
            ],
            chart: {
                type: 'line',
                height: 350,
                toolbar: { show: true }
            },
            colors: ['#28a745', '#ffc107'],
            stroke: {
                curve: 'smooth',
                dashArray: [0, 5],
                width: 2
            },
            xaxis: {
                categories: (months.slice(-6) || []).concat(forecastMonths)
            },
            yaxis: {
                title: { text: 'Number of RFQs' }
            },
            markers: {
                size: 4
            },
            tooltip: {
                theme: 'light'
            }
        };

        if (window.ApexCharts) {
            const chart = new ApexCharts(chartDiv, options);
            chart.render();
        } else {
            chartDiv.innerHTML = '<p class="text-danger">ApexCharts library not loaded</p>';
        }
    } catch (e) {
        console.error('Error rendering Volume Forecast chart:', e);
        chartDiv.innerHTML = '<p class="text-danger">Error loading chart</p>';
    }
}
