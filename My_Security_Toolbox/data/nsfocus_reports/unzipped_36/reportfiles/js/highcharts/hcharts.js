function formatPoint(point){
	var pointStr = point.toFixed(1);
	if(point > 9.9){
		pointStr = point.toFixed(0);
	}
	return pointStr;
}

function onSpotClick(url){
	top.dialog.show({title:'详情',url:url});
}

/*
 * common default setting of highcharts
 */
var chartoption = {
    chart: {
        backgroundColor: '#FFFFFF',
        spacingLeft:0,// 边距
        spacingRigth:0,
        spacingTop:0,
        spacingBottom:0
    },
    xAxis: {
        tickWidth: 1,//刻度
        tickLength: 5,
        gridLineColor: "#c0c0c0", //格线的颜色
        tickPosition: "outside",
        lineWidth: 1,//x轴宽度
        lineColor: "#c0c0c0", //轴颜色
        tickColor: "#c0c0c0", //刻度颜色
        labels:{
            rotation: -45,
            y: 30
        }
    },
    yAxis: {
        tickWidth: 1,//刻度
        tickLength: 5,
        tickPosition: "outside",
        lineWidth: 1,//y轴宽度
        lineColor: "#c0c0c0", //轴颜色
        tickColor: "#c0c0c0" //刻度颜色
    },
    plotOptions: {
    	enabled: false
    },
    exporting: {
        enabled : false
    },
    credits: {
        enabled: false
    },
    legend: {
    	backgroundColor: "#FFFFFF",
    	layout: 'horizontal',
    	align: 'center',
    	verticalAlign: 'bottom',
    	borderWidth: 0,
    	shadow: false,
    	labelFormatter: function() {
            return '<span style="font-size:12px;color:#aaaaaa;">'+this.name+'</span>';
        }
    },
    global: { 
        useUTC: false 
    } 
}
Highcharts.setOptions(chartoption);
/*
 * draw a piechart
 * renderTo: id of renderTo tag
 * title: title of chart
 * data: json format:[["example1",4],["example2",3],["example3",2],["example4",1]]
 * showInLegend: bool
 */
function drawPiechart(renderTo,title,items,data,showInLegend){
    var chart;
    $(document).ready(function() {
        if(!$("#"+renderTo).length){
            return false
        }
        var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;
        if(items.length==1){
            items[0].style.left = width/2-50;
            items[0].style.top = height/3+3*height/16+15;
        }
        else if(items.length==3){
            items[0].style.left = (width/2-height/2)-50;	//items[0~2]是三个图的标题
            items[0].style.top = height/3+3*height/16+15;
            items[1].style.left = width/2-50;
            items[1].style.top = height/3+3*height/16+15;
            items[2].style.left = (width/2+height/2)-50;
            items[2].style.top = height/3+3*height/16+15;
        }
        if(data.length==1){
            var series = [{
	            data: data[0],//传入参数
	            size: height/2,
            	center: [width/2, (height/3-height/16)]
	        }]
        }
        else if(data.length==3){
            var series = [{
                data: data[0],//传入参数
                size: height/4,
                center: [(width/2-height/2), (height/3+height/16)],
                showInLegend: false
            },{
	            data: data[1],//传入参数
	            size: height/2,
            	center: [width/2, (height/3-height/16)]
	        },{
		        data: data[2],//传入参数
		        size: height/4,
		        center: [(width/2+height/2), (height/3+height/16)],
		        showInLegend: false
		    }]
        }
        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,//传入参数  
                type: 'pie'
            },
            title: {
                text: ' '//传入参数
            },
            tooltip: {
                pointFormat: "{point.percentage}\n%({point.y})",
                percentageDecimals: 1
            },
            plotOptions: {
                pie: {
                	shadow: false,
                    allowPointSelect: false,
                    cursor: 'pointer',
                    dataLabels: {
                        enabled: false,
                        color: '#000000',
                        distance: -10,
                        formatter: function() {
                            if(this.y == 0) return ""//不显示空值
                            return this.percentage.toFixed(0)+' %';
                        }
                    },
                    showInLegend: showInLegend,//传入参数
                    events:{
                        click: function(event){
                        	onSpotClick(event.point.url);
                        }
                    },
                    point: {
                    	events: {
                            //控制图标的图例legend不允许切换
                            legendItemClick: function (event) {                                    
                                return false; //return  true 则表示允许切换
                            }
                        }
                    }
                }
            },
            labels: {
                items: items
            },
            series: series
        });
    });
}

function drawP(renderTo,data){
	 var chart;
    $(document).ready(function() {
        if(!$("#"+renderTo).length){
            return false
        }
        var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;

        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,//传入参数  
                type: 'pie'
            },
            title: {
                text: ' '//传入参数
            },
            tooltip: {
                pointFormat: "{point.percentage}\n%({point.y})",
                percentageDecimals: 1
            },
            plotOptions: {
                pie: {
                	shadow: false,
                    allowPointSelect: false,
                    cursor: 'pointer',
                    dataLabels: {
                        enabled: false,
                        color: '#000000',
                        distance: -10,
                        formatter: function() {
                            if(this.y == 0) return ""//不显示空值
                            return this.percentage.toFixed(0)+' %';
                        }
                    },
                    showInLegend: false,//传入参数
                    events:{
                        click: function(event){
                        	onSpotClick(event.point.url);
                        }
                    },
                    point: {
                    	events: {
                            //控制图标的图例legend不允许切换
                            legendItemClick: function (event) {                                    
                                return false; //return  true 则表示允许切换
                            }
                        }
                    }
                }
            },
            series: [{
                data: data,//传入参数
                size: height-35,
                //center: [(width/2-height/2), (height/3+height/16)],
                showInLegend: false
            }]
        });
    });
 }

/*
 * draw a linechart
 * renderTo: id of renderTo tag
 * title: title of chart
 * data: json format:[["example1",4],["example2",3],["example3",2],["example4",1]]
 */
function drawLinechart(renderTo,title,yAxis,xAxis,items,data,showInLegend){
    var chart;
    $(document).ready(function() {
        if(!$("#"+renderTo).length){
            return false
        }
        var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;
        items[0].style.left = width/2-130;
        items[0].style.top = height/3;
        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,//传入参数
                type: 'line'
            },
            title: {
                text: title,//传入参数
                align: 'right',
                style: {
                	fontSize: '12px',
                	color: '#a0a0a0'
                }
            },
            yAxis: yAxis,	//传入参数
            xAxis: xAxis,	//传入参数
            scrollbar: {
            	enabled: true
        	},
            tooltip: {
            	valueDecimals: 1
                /*formatter: function() {
                    return yAxis['title']['text'] + "：" + this.y.toFixed(1);
                }*/
            },
            labels: {
                items: items
            },
            plotOptions: {
                line:{
                	shadow: false,
                    showInLegend: showInLegend || false,//传入参数 默认是false
                    events:{
                        click: function(event){
                        	if(event.point.y!=0)
                        		onSpotClick(event.point.url);
                        }
                    }
                }
            },
            series: data//传入参数
        });
    });
}

/*
 * draw a columnchart
 * renderTo: "#container"
 * data:[{
            "name": '低',
            "data": [48, 16, 2, 5, 2],
            "color": '#4474C4',
        }, {
            "name": '中',
            "data": [8, 31, 2, 27, 8],
            "color": '#FFC000',
        },{
            "name": '高',
            "data": [10, 18, 0, 25, 6],
            "color": '#CC0000',
        }],
 * option: title of chart
 */
function drawColumnchart(renderTo,title,yAxis,xAxis,items,data,value,showInLegend){
    var chart;
    $(document).ready(function() {
        if(!$("#"+renderTo).length){
            return false
        }
        var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;
        items[2].style.left = width/2-130;
        items[2].style.top = height/3;
        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,//传入参数
                type: 'column'
            },
            title: {
                text: title,//传入参数
                align: 'right',
                style: {
                	fontSize: '12px',
                	color: '#a0a0a0'
                }
            },
            yAxis: yAxis,	//传入参数
            xAxis: xAxis,	//传入参数
            tooltip: {
                /*formatter: function() {
                    return "风险值：" + this.y;
                }*/
            },
            labels: {
                items: items
            },
            plotOptions: {
                column: {
                	shadow: false,
                    stacking: 'normal',
                    showInLegend: showInLegend || false,//传入参数 默认是false
                    events:{
                        click: function(event){
                        	if(event.point.y!=0)
                        		onSpotClick(event.point.url);
                        },
                        legendItemClick: function (event) {                                    
                            return false; //return  true 则表示允许切换
                        }
                    }
                }
            },
            series: data//传入参数
        });
    });
}

function drawRingchart(renderTo,title,data,value,showInLegend){
	var chart;
    $(document).ready(function() {
    	if(!$("#"+renderTo).length){
            return false
        }
    	var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;
    
        //解决浏览器兼容性问题
        var distance = [0, 0, 0];
        var font_size = [0, 0, 0, 0, 0, 0];
        
        if(value['data'].length==1){
            if(window.screen.height <= 768){
                font_size = [14, 7, 30, 12, 14, 7];
                if(document.all){ //IE
                    if(value['data'][0]==0)
                        distance[0] = -38;
                    else
                        distance[0] = -60;
                }
                else{	//other
                    if(value['data'][0]==0)
                        distance[0] = -55;
                    else
                        distance[0] = -45;
                }
            }
            else{
                font_size = [24, 11, 40, 16, 24, 11];
                if(document.all){ //IE
                    if(value['data'][0]==0)
                        distance[0] = -50;
                    else
                        distance[0] = -85;
                }
                else{	//other
                    if(value['data'][0]==0)
                        distance[0] = -80;
                    else
                        distance[0] = -60;
                }
            }
            //end
        }
        else if(value['data'].length==3){
            if(window.screen.height <= 768){
                font_size = [14, 7, 30, 12, 14, 7];
                if(document.all){ //IE
                    if(value['data'][0]==0)
                        distance[0] = -23;
                    else
                        distance[0] = -27;
                    if(value['data'][1]==0)
                        distance[1] = -38;
                    else
                        distance[1] = -60;
                    if(value['data'][2]==0)
                        distance[2] = -23;
                    else
                        distance[2] = -27;
                }
                else{	//other
                    if(value['data'][0]==0)
                        distance[0] = -24;
                    else
                        distance[0] = -24;
                    if(value['data'][1]==0)
                        distance[1] = -55;
                    else
                        distance[1] = -45;
                    if(value['data'][2]==0)
                        distance[2] = -24;
                    else
                        distance[2] = -24;
                }
            }
            else{
                font_size = [24, 11, 40, 16, 24, 11];
                if(document.all){ //IE
                    if(value['data'][0]==0)
                        distance[0] = -27;
                    else
                        distance[0] = -42;
                    if(value['data'][1]==0)
                        distance[1] = -50;
                    else
                        distance[1] = -85;
                    if(value['data'][2]==0)
                        distance[2] = -27;
                    else
                        distance[2] = -42;
                }
                else{	//other
                    if(value['data'][0]==0)
                        distance[0] = -40;
                    else
                        distance[0] = -32;
                    if(value['data'][1]==0)
                        distance[1] = -80;
                    else
                        distance[1] = -60;
                    if(value['data'][2]==0)
                        distance[2] = -40;
                    else
                        distance[2] = -32;
                }
            }
            //end
        }
        
        if(data.length==1){
            var innerData = [[{name:value['text'][0], y:value['data'][0], color:'#FFF'}]];
            var series = [{
	                name: value['text'][0],
	                data: innerData[0],
	                size: height/2,
		            center: [width/2, (height/3-height/16)],
		            showInLegend: false,
	                dataLabels: {
	                    formatter: function() {
	                        return '<div><span style="font-family:Arial;font-size:'+font_size[2]+'px;color:'+value['color'][0]+'">'+formatPoint(value['data'][0])+'</span><span style="font-family:'+"'微软雅黑'"+';font-size:'+font_size[3]+'px;font-weight:bold;color:'+value['color'][0]+'">分</span></div>';
	                    },
	                    distance: distance[0]
	                }
	            }, {
	                name: value['text'][0],
	                data: data[0],
	                size: height/2,
		            center: [width/2, (height/3-height/16)],
	                innerSize: '50%',
	                dataLabels: {
	                    formatter: function() {
	                        return  null;
	                    }
	                }
	            }
	        ]
        }
        else if(data.length==3){
            var innerData = [[{name:value['text'][0], y:value['data'][0], color:'#FFF'}],
                             [{name:value['text'][1], y:value['data'][1], color:'#FFF'}],
                             [{name:value['text'][2], y:value['data'][2], color:'#FFF'}]];
                         
            var series = [{
	                name: value['text'][0],
	                data: innerData[0],
	                size: height/4,
	                center: [(width/2-height/2), (height/3+height/16)],
	                showInLegend: false,
	                dataLabels: {
	                    formatter: function() {
	                    	return '<div><span style="font-family:Arial;font-size:'+font_size[0]+'px;color:'+value['color'][0]+'">'+formatPoint(value['data'][0])+'</span><span style="font-family:'+"'微软雅黑'"+';font-size:'+font_size[1]+'px;font-weight:bold;color:'+value['color'][0]+'">分</span></div>';
	                    },
	                    distance: distance[0]
	                }
	            }, {
	                name: value['text'][0],
	                data: data[0],
	                size: height/4,
	                center: [(width/2-height/2), (height/3+height/16)],
	                showInLegend: false,
	                innerSize: '25%',
	                dataLabels: {
	                    formatter: function() {
	                        return  null;
	                    }
	                }
	            }, {
	                name: value['text'][1],
	                data: innerData[1],
	                size: height/2,
		            center: [width/2, (height/3-height/16)],
		            showInLegend: false,
	                dataLabels: {
	                    formatter: function() {
	                        return '<div><span style="font-family:Arial;font-size:'+font_size[2]+'px;color:'+value['color'][1]+'">'+formatPoint(value['data'][1])+'</span><span style="font-family:'+"'微软雅黑'"+';font-size:'+font_size[3]+'px;font-weight:bold;color:'+value['color'][1]+'">分</span></div>';
	                    },
	                    distance: distance[1]
	                }
	            }, {
	                name: value['text'][1],
	                data: data[1],
	                size: height/2,
		            center: [width/2, (height/3-height/16)],
	                innerSize: '50%',
	                dataLabels: {
	                    formatter: function() {
	                        return  null;
	                    }
	                }
	            }, {
	                name: value['text'][2],
	                data: innerData[2],
	                size: height/4,
			        center: [(width/2+height/2), (height/3+height/16)],
			        showInLegend: false,
	                dataLabels: {
	                    formatter: function() {
	                    	return '<div><span style="font-family:Arial;font-size:'+font_size[4]+'px;color:'+value['color'][2]+'">'+formatPoint(value['data'][2])+'</span><span style="font-family:'+"'微软雅黑'"+';font-size:'+font_size[5]+'px;font-weight:bold;color:'+value['color'][2]+'">分</span></div>';
	                    },
	                    distance: distance[2]
	                }
	            }, {
	                name: value['text'][2],
	                data: data[2],
	                size: height/4,
			        center: [(width/2+height/2), (height/3+height/16)],
			        showInLegend: false,
	                innerSize: '25%',
	                dataLabels: {
	                    formatter: function() {
	                        return  null;
	                    }
	                }
	            }
	        ]
        }
    
        // Create the chart
        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,
                type: 'pie',
                events: {
                	load: function(){
                		$($('.highcharts-legend-item')[4]).css('display','none');	//去掉外层环的灰色图例
                	}
                }
            },
            title: title,
            plotOptions: {
                pie: {
                    shadow: false,
                    showInLegend: showInLegend,//传入参数
                    events:{
                        click: function(event){
                        	if(event.point.name!=' ')
                        		onSpotClick(event.point.url);
                        }
                    },
                    point: {
                    	events: {
                            //控制图标的图例legend不允许切换
                            legendItemClick: function (event) {                                    
                                return false; //return  true 则表示允许切换
                            }
                        }
                    }
                }
            },
            tooltip: {
            	formatter: function() {
            		if(this.key!=' ')
            			return value['text'][3] + "：" + this.y.toFixed(1);
            		else
            			return value['text'][3] + "：" + (10-this.y).toFixed(1);
            	}
            },
            labels: {
                items: [{
                    html: value['text'][0],
                    style: {
                    	fontSize: '12px',
                    	color: '#aaaaaa',
                        left: (width/2-height/2)-30,
                        top: height/3+3*height/16+15
                    }
                },{
                    html: value['text'][1],
                    style: {
                    	fontSize: '12px',
                    	color: '#aaaaaa',
                        left: width/2-30,
                        top: height/3+3*height/16+15
                    }
                },{
                    html: value['text'][2],
                    style: {
                    	fontSize: '12px',
                    	color: '#aaaaaa',
                        left: (width/2+height/2)-30,
                        top: height/3+3*height/16+15
                    }
                }]
            },
            series: series
        });
    });
}

function drawR(renderTo,data,value,innerSize){
	var chart;
    $(document).ready(function() {
    	if(!$("#"+renderTo).length){
            return false
        }
    	var width = $("#"+renderTo)[0].clientWidth;
        var height = $("#"+renderTo)[0].clientHeight;
		
		var innerData = [{name:value['text'], y:value['data'], color:'#FFF'}];
		var font_size = [24, 11, 40, 16, 24, 11];
     // Create the chart
        chart = new Highcharts.Chart({
            chart: {
                renderTo: renderTo,
                type: 'pie'
            },
            title: '',
            plotOptions: {
                pie: {
                    shadow: false,
                    showInLegend: false,//传入参数
                    events:{
                        click: function(event){
                        	if(event.point.name!=' ')
                        		onSpotClick(event.point.url);
                        }
                    },
                    point: {
                    	events: {
                            //控制图标的图例legend不允许切换
                            legendItemClick: function (event) {                                    
                                return false; //return  true 则表示允许切换
                            }
                        }
                    }
                }
            },
            tooltip: {
            	formatter: function() {
            		return false
            	}
            },
			
            series: [{
	                name: value['text'],
	                data: innerData,
	                showInLegend: false,
	                dataLabels: {
	                    formatter: function() {
	                    	//return false;//'<div><span style="font-family:Arial;font-size:'+font_size[0]+'px;color:'+value['color']+'">'+formatPoint(value['data'])+'</span><span style="font-family:'+"'微软雅黑'"+';font-size:'+font_size[1]+'px;font-weight:bold;color:'+value['color']+'">分</span></div>';
	                    }
	                }
	            }, {
	                name: value['text'],
	                data: data,
	                size: height-10,
	                showInLegend: false,
	                innerSize: innerSize,
	                dataLabels: {
	                    formatter: function() {
	                        return  null;
	                    }
	                }
	            
	            }
	        ]
        });
    });

}

/*
 * draw a gaugechart
 * title: title of chart
 * data: json format:[["example1",4],["example2",3],["example3",2],["example4",1]]
 * renderTo: id of renderTo tag
 */
function drawGaugechart(renderTo,title,data){
    var chart;
    var percent = "60%"
    var categories = ['NO','0','1','2','3','4','5','6','7','8','9','10',]
    var colorList = ['#47594F', '#30C200', '#66FF00', '#E7FF00', '#FFFF00', '#FFCC00', '#F9A30B', '#FF8603', '#FC5615', '#FF0000', '#CC0000']
    var plotBands = new Array();
    for(var i=0;i<colorList.length;i++){
        plotBands[i] = {
            from: i,
            to: i+1,
            innerRadius: "100%",
            outerRadius: "140%",
            color: colorList[i]
        }
    }
    $(document).ready(function() {
        if(!$("#"+renderTo).length){
            return false
        }
        var width = $("#"+renderTo).width();
        var height = $("#"+renderTo).height();
        var minsize = width<height?width:height
        chart = new Highcharts.Chart({
            chart: {
                backgroundColor: '#FFFFFF',
                shadow: true,
                renderTo: renderTo, // 传入参数
                type: 'gauge'
            },
            
            title: {
                text: title, //传入参数
                align:"center",
                verticalAlign:"bottom"
            },
            pane: {
                startAngle: -85,
                endAngle: 85,
                center: [width / 2, height * 0.8],//pane center
                background: null
            },
            plotOptions: {
                gauge: {
                    dataLabels: {
                        enabled: true,
                        formatter: function() {
                            return "资产风险值：" + this.y + "分";
                        },
                        borderWidth:0
                    },
                    dial: {
                        radius: percent,// 自定义参数
                        rearLength: "20%"
                    },
                    pivot:{
                        radius: 6,
                        center:[0,0]
                    }
                }
            },
            yAxis: {
                min: 0,
                max: 11,
                categories: categories,
                minorTickLength: 0,
                minorTickColor: '#FFF',
                tickLength: 0,
                tickWidth: 0,
                tickInterval: 1,
                tickmarkPlacement: "on",
                labels: {
                    step: 1,
                    align: 'center',
                    style:{
                        color: "#333",
                        fontWeight: 'bold',
                        fontSize: '12px'
                    }
                },
                plotBands: plotBands
            },
            series: [{
                name: "风险值",
                data: [data,] // 传入参数
            }]
        });
    });
}