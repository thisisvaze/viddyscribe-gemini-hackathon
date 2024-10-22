import React from 'react'
import { FaDiscord, FaGoogle, FaEnvelope, FaNewspaper, FaRegNewspaper, FaCircle, FaNode } from 'react-icons/fa'

const Footer = () => {
    return (
      <div className="flex flex-col mb-6 align-center justify-center text-center">
        <div className="flex flex-col align-center justify-center text-center">
          <div className="flex text-zinc-100/60 space-x-8 flex-row align-center justify-center text-center">
            <a href="https://discord.gg/zASd8nt4" target="_blank" className="text-sm hover:underline flex items-center">
              <FaDiscord className="mr-2" /> {/* Add margin-right */}
              Join Discord
            </a>
            <a href="mailto:viddyscribe@gmail.com" target="_blank" className="text-sm hover:underline flex items-center">
              <FaEnvelope className="mr-2" /> {/* Add margin-right */}
              Get Support
            </a>
            <a href="https://forms.gle/HzBnT5MMketPV9rn7" target="_blank" className="text-sm hover:underline flex items-center">
              <FaCircle className="mr-2" /> {/* Add margin-right */}
              Sign Up for Newsletter
            </a>
          </div>
          <hr className="my-2 border-zinc-100/40" /> {/* Add separator */}
          <p className="text-zinc-100/40 mt-0 text-sm">
            <span className=""> Powered by Gemini 1.5 Pro | </span>
            <a href="https://ai.google.dev/competition/projects/viddyscribe" target="_blank" className="hover:underline  font-bold text-sm">
              Built for Gemini API Developer Competition
            </a>
          </p>
        </div>
      </div>
    )
}
export default Footer