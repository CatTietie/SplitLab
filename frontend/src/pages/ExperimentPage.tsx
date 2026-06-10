import { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, Descriptions, Tag, Button, Space, Input, message, Statistic, Row, Col, Alert, notification } from 'antd'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ErrorBar, ResponsiveContainer } from 'recharts'
import { experimentApi } from '../api'
import { useSSE, type SSEEvent } from '../hooks/useSSE'
import RolloutProgress from '../components/RolloutProgress'

const statusColors: Record<string, string> = {
  draft: 'default',
  running: 'green',
  paused: 'orange',
  full_rollout: 'blue',
  archived: 'red',
}

function ExperimentPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [goalEvent, setGoalEvent] = useState('conversion')

  const { data: experiment } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentApi.get(id!),
    enabled: !!id,
  })

  const handleSSE = useCallback((event: SSEEvent) => {
    if (event.type === 'rollout_guardrail_warning') {
      const severity = event.payload.severity as string
      if (severity === 'critical') {
        notification.error({
          message: '护栏指标异常',
          description: `指标 ${event.payload.metric_name} 恶化超过阈值，已自动回退`,
        })
      } else {
        notification.warning({
          message: '护栏指标警告',
          description: `指标 ${event.payload.metric_name} 轻微恶化，请关注`,
        })
      }
    } else if (event.type === 'rollout_step_rolled_back') {
      notification.info({ message: '灰度已回退', description: `已回退到步骤 ${(event.payload.step_index as number) + 1}` })
    } else if (event.type === 'rollout_step_advanced') {
      notification.success({ message: '灰度已推进', description: `流量已扩至 ${event.payload.traffic_percentage}%` })
    }
  }, [])

  useSSE(id, handleSSE)

  const { data: stats } = useQuery({
    queryKey: ['stats', id, goalEvent],
    queryFn: () => experimentApi.stats(id!, goalEvent),
    enabled: !!id && !!experiment && experiment.status !== 'draft',
  })

  const startMutation = useMutation({
    mutationFn: () => experimentApi.start(id!),
    onSuccess: () => { message.success('实验已启动'); queryClient.invalidateQueries({ queryKey: ['experiment', id] }) },
  })

  const pauseMutation = useMutation({
    mutationFn: () => experimentApi.pause(id!),
    onSuccess: () => { message.success('实验已暂停'); queryClient.invalidateQueries({ queryKey: ['experiment', id] }) },
  })

  const resumeMutation = useMutation({
    mutationFn: () => experimentApi.resume(id!),
    onSuccess: () => { message.success('实验已恢复'); queryClient.invalidateQueries({ queryKey: ['experiment', id] }) },
  })

  if (!experiment) return null

  const chartData = stats?.groups.map(g => ({
    name: g.group_name,
    conversion_rate: +(g.conversion_rate * 100).toFixed(2),
    ci_lower: +((g.conversion_rate - g.ci_lower) * 100).toFixed(2),
    ci_upper: +((g.ci_upper - g.conversion_rate) * 100).toFixed(2),
  })) || []

  return (
    <div>
      <Card title={experiment.name} extra={<Tag color={statusColors[experiment.status]}>{experiment.status}</Tag>}>
        <Descriptions column={2}>
          <Descriptions.Item label="Key">{experiment.key}</Descriptions.Item>
          <Descriptions.Item label="流量范围">{experiment.bucket_start} - {experiment.bucket_end}</Descriptions.Item>
          <Descriptions.Item label="描述">{experiment.description || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{new Date(experiment.created_at).toLocaleString()}</Descriptions.Item>
        </Descriptions>

        <div style={{ marginTop: 16 }}>
          <h4>实验组</h4>
          {experiment.groups.map(g => (
            <Tag key={g.id}>{g.name}: {g.traffic_percentage}%</Tag>
          ))}
        </div>

        <Space style={{ marginTop: 16 }}>
          {experiment.status === 'draft' && (
            <Button type="primary" onClick={() => startMutation.mutate()}>启动实验</Button>
          )}
          {experiment.status === 'running' && (
            <Button onClick={() => pauseMutation.mutate()}>暂停</Button>
          )}
          {experiment.status === 'paused' && (
            <Button type="primary" onClick={() => resumeMutation.mutate()}>恢复</Button>
          )}
          {(experiment.status === 'running' || experiment.status === 'paused') && experiment.groups.length > 0 && !experiment.rollout_steps && (
            <Button
              type="primary"
              danger
              onClick={() => {
                const winner = experiment.groups[experiment.groups.length - 1]
                experimentApi.rollout(id!, winner.id).then(() => {
                  message.success('已全量发布')
                  queryClient.invalidateQueries({ queryKey: ['experiment', id] })
                })
              }}
            >
              全量发布 (Treatment)
            </Button>
          )}
        </Space>

        {experiment.status === 'running' && experiment.rollout_steps && experiment.current_step_index !== null && (
          <RolloutProgress experiment={experiment} />
        )}
      </Card>

      {experiment.status !== 'draft' && (
        <Card title="统计分析" style={{ marginTop: 16 }}>
          <Space style={{ marginBottom: 16 }}>
            <Input
              value={goalEvent}
              onChange={e => setGoalEvent(e.target.value)}
              placeholder="目标事件名"
              style={{ width: 200 }}
            />
          </Space>

          {stats && (
            <>
              <Row gutter={16} style={{ marginBottom: 16 }}>
                {stats.groups.map(g => (
                  <Col span={8} key={g.group_name}>
                    <Statistic
                      title={`${g.group_name} 转化率`}
                      value={(g.conversion_rate * 100).toFixed(2)}
                      suffix="%"
                      precision={2}
                    />
                    <div style={{ fontSize: 12, color: '#888' }}>
                      {g.total_users} 用户, {g.conversions} 转化
                    </div>
                  </Col>
                ))}
                <Col span={8}>
                  <Statistic
                    title="P-Value"
                    value={stats.p_value?.toFixed(4) || 'N/A'}
                  />
                </Col>
              </Row>

              {stats.is_significant && (
                <Alert message="结果具有统计显著性 (p < 0.05)" type="success" style={{ marginBottom: 16 }} />
              )}

              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis label={{ value: '转化率 (%)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Bar dataKey="conversion_rate" fill="#1890ff">
                    <ErrorBar dataKey="ci_upper" width={4} strokeWidth={2} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
        </Card>
      )}
    </div>
  )
}

export default ExperimentPage
