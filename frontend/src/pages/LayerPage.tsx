import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Table, Button, Modal, Form, Input, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { layerApi, Layer } from '../api'

function LayerPage() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: layers, isLoading } = useQuery({
    queryKey: ['layers'],
    queryFn: () => layerApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: layerApi.create,
    onSuccess: () => {
      message.success('流量层创建成功')
      setCreateOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['layers'] })
    },
  })

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'Salt', dataIndex: 'salt', key: 'salt', render: (v: string) => v.substring(0, 8) + '...' },
    { title: '描述', dataIndex: 'description', key: 'description', render: (v: string | null) => v || '-' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => new Date(v).toLocaleString() },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>流量层管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          创建流量层
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={layers || []}
        loading={isLoading}
        rowKey="id"
      />

      <Modal
        title="创建流量层"
        open={createOpen}
        onOk={() => form.validateFields().then(v => createMutation.mutate(v))}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="层名称" rules={[{ required: true }]}>
            <Input placeholder="如 homepage_tests" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default LayerPage
