import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Table, Button, Tag, Space, Modal, Form, Input, Select, InputNumber, message, Divider, Switch } from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { experimentApi, layerApi, Experiment } from '../api'

const statusColors: Record<string, string> = {
  draft: 'default',
  running: 'green',
  paused: 'orange',
  full_rollout: 'blue',
  archived: 'red',
}

function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [enableRollout, setEnableRollout] = useState(false)
  const [form] = Form.useForm()

  const { data, isLoading } = useQuery({
    queryKey: ['experiments'],
    queryFn: () => experimentApi.list(),
  })

  const { data: layers } = useQuery({
    queryKey: ['layers'],
    queryFn: () => layerApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: experimentApi.create,
    onSuccess: () => {
      message.success('实验创建成功')
      setCreateOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
  })

  const columns = [
    { title: '实验名称', dataIndex: 'name', key: 'name' },
    { title: 'Key', dataIndex: 'key', key: 'key' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={statusColors[status]}>{status}</Tag>,
    },
    {
      title: '流量范围',
      key: 'traffic',
      render: (_: unknown, record: Experiment) =>
        `${record.bucket_start} - ${record.bucket_end} (${((record.bucket_end - record.bucket_start + 1) / 100).toFixed(1)}%)`,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => new Date(v).toLocaleString() },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Experiment) => (
        <Button type="link" onClick={() => navigate(`/experiments/${record.id}`)}>详情</Button>
      ),
    },
  ]

  const handleCreate = async () => {
    const values = await form.validateFields()
    const groups = [
      { name: 'control', traffic_percentage: values.control_pct },
      { name: 'treatment', traffic_percentage: 100 - values.control_pct },
    ]
    const payload: Parameters<typeof experimentApi.create>[0] = {
      layer_id: values.layer_id,
      key: values.key,
      name: values.name,
      description: values.description,
      bucket_start: values.bucket_start,
      bucket_end: values.bucket_end,
      groups,
    }
    if (enableRollout && values.rollout_steps?.length) {
      payload.rollout_steps = values.rollout_steps
    }
    if (enableRollout && values.guardrail_metrics?.length) {
      payload.guardrail_metrics = values.guardrail_metrics
    }
    createMutation.mutate(payload)
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>实验列表</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          创建实验
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data?.items || []}
        loading={isLoading}
        rowKey="id"
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="创建实验"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="layer_id" label="流量层" rules={[{ required: true }]}>
            <Select placeholder="选择流量层">
              {layers?.map(l => <Select.Option key={l.id} value={l.id}>{l.name}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="key" label="实验 Key" rules={[{ required: true }]}>
            <Input placeholder="唯一标识，如 homepage_cta" />
          </Form.Item>
          <Form.Item name="name" label="实验名称" rules={[{ required: true }]}>
            <Input placeholder="实验显示名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea />
          </Form.Item>
          <Space>
            <Form.Item name="bucket_start" label="桶起始" rules={[{ required: true }]} initialValue={0}>
              <InputNumber min={0} max={9999} />
            </Form.Item>
            <Form.Item name="bucket_end" label="桶结束" rules={[{ required: true }]} initialValue={9999}>
              <InputNumber min={0} max={9999} />
            </Form.Item>
          </Space>
          <Form.Item name="control_pct" label="对照组流量%" rules={[{ required: true }]} initialValue={50}>
            <InputNumber min={1} max={99} />
          </Form.Item>

          <Divider />
          <div style={{ marginBottom: 16 }}>
            <Space>
              <span>启用灰度发布</span>
              <Switch checked={enableRollout} onChange={setEnableRollout} />
            </Space>
          </div>

          {enableRollout && (
            <>
              <Form.List name="rollout_steps" initialValue={[{ traffic_percentage: 5, hold_seconds: 600 }, { traffic_percentage: 20, hold_seconds: 1800 }, { traffic_percentage: 50, hold_seconds: 3600 }, { traffic_percentage: 100, hold_seconds: 0 }]}>
                {(fields, { add, remove }) => (
                  <>
                    <div style={{ marginBottom: 8, fontWeight: 500 }}>灰度步骤</div>
                    {fields.map((field) => (
                      <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                        <Form.Item {...field} name={[field.name, 'traffic_percentage']} rules={[{ required: true }]} noStyle>
                          <InputNumber min={1} max={100} placeholder="流量%" addonAfter="%" />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'hold_seconds']} rules={[{ required: true }]} noStyle>
                          <InputNumber min={0} placeholder="停留秒数" addonAfter="秒" />
                        </Form.Item>
                        <MinusCircleOutlined onClick={() => remove(field.name)} />
                      </Space>
                    ))}
                    <Button type="dashed" onClick={() => add({ traffic_percentage: 50, hold_seconds: 1800 })} icon={<PlusOutlined />}>
                      添加步骤
                    </Button>
                  </>
                )}
              </Form.List>

              <Form.List name="guardrail_metrics">
                {(fields, { add, remove }) => (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 500 }}>护栏指标 (可选)</div>
                    {fields.map((field) => (
                      <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                        <Form.Item {...field} name={[field.name, 'metric_name']} rules={[{ required: true }]} noStyle>
                          <Input placeholder="指标名" style={{ width: 120 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'threshold']} rules={[{ required: true }]} noStyle>
                          <InputNumber min={0.001} step={0.01} placeholder="阈值" />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'direction']} rules={[{ required: true }]} noStyle>
                          <Select placeholder="方向" style={{ width: 100 }}>
                            <Select.Option value="up">上升为异常</Select.Option>
                            <Select.Option value="down">下降为异常</Select.Option>
                          </Select>
                        </Form.Item>
                        <MinusCircleOutlined onClick={() => remove(field.name)} />
                      </Space>
                    ))}
                    <Button type="dashed" onClick={() => add({ metric_name: '', threshold: 0.05, direction: 'up' })} icon={<PlusOutlined />}>
                      添加护栏指标
                    </Button>
                  </div>
                )}
              </Form.List>
            </>
          )}
        </Form>
      </Modal>
    </div>
  )
}

export default Dashboard
