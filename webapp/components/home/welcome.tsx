import { getUser } from '@/lib/auth-server'

export default async function WelcomeBanner() {
  const user = await getUser()
  if (!user) return null
  const firstName = (user.name || user.email).split(' ')[0]

  return (
    <div>
      <h1 className="text-2xl font-bold text-[#e7e9ee]">
        Good to see you, {firstName}
      </h1>
      <p className="text-[#9aa3b2] mt-1 text-sm">{user.email}</p>
    </div>
  )
}

